"""Red flags for human review: Isolation Forest + 5 transparent rules (spec M6.1, US-18).

The output is a ranked list of *leads*, never accusations. Each flagged contract carries
stable reason ids (``split_contract``, ``under_threshold``, ``single_bidder``,
``fy_end_spike``, ``new_large_supplier``, ``unusual_pattern``) that the API localizes, and
the top of the list carries SHAP feature contributions to the anomaly score.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from app.core.cleaning.ops import FxTable
from app.core.ml import SEED
from app.core.ml.shapley import shapley_values

RULES = ("split_contract", "under_threshold", "single_bidder", "fy_end_spike", "new_large_supplier")
FEATURES = (
    "amount_cad",
    "days_to_fy_end",
    "n_bidders",
    "supplier_age_days",
    "entity_share",
    "days_between_contracts",
    "gap_to_threshold",
)

# Award thresholds per jurisdiction, in local currency (approximate; set per jurisdiction).
# CA: federal competitive thresholds (goods 25 k, services 40 k) and the trade-agreement
# threshold for goods/services; QC: public call for tenders (LCOP / CETA); CO: mínima and
# menor cuantía of a large entity (100 and 1,000 SMMLV of 2025, COP 1,423,500).
THRESHOLDS: dict[str, tuple[str, tuple[float, ...]]] = {
    "CA": ("CAD", (25_000.0, 40_000.0, 133_800.0)),
    "QC": ("CAD", (25_000.0, 133_800.0)),
    "CO": ("COP", (142_350_000.0, 1_423_500_000.0)),
}
UNDER_BAND = 0.10  # "just under" = within 10 % below a threshold
SPLIT_DAYS = 7
FY_END_DAYS = 30
FY_SPIKE_RATIO = 2.0
NEW_SUPPLIER_DAYS = 90
LARGE_QUANTILE = 0.95
UNUSUAL_PERCENTILE = 0.99
N_TREES = 200
TOP_N = 50
EXPLAINED = 10
BACKGROUND = 100


@dataclass(frozen=True)
class RedFlagParams:
    jurisdiction: str
    contamination: float = 0.01
    top_n: int = TOP_N


def _thresholds_cad(df: pd.DataFrame, jurisdiction: str, fx: FxTable) -> np.ndarray:
    """Matrix (rows × thresholds) of thresholds converted to CAD with each row's month rate."""
    currency, values = THRESHOLDS.get(jurisdiction, THRESHOLDS["CA"])
    if currency == "CAD":
        return np.tile(np.array(values), (len(df), 1))
    months = df["date"].dt.strftime("%Y-%m").fillna("")
    rates = {m: fx.cad_per_unit(currency, m) for m in months.unique()}
    rate = months.map(lambda m: rates.get(m) or np.nan).to_numpy(dtype=float)
    return rate[:, None] * np.array(values)[None, :]


def build_features(df: pd.DataFrame, jurisdiction: str, fx: FxTable) -> pd.DataFrame:
    """Per-contract features and rule inputs. ``df`` comes from the star schema (see
    ``app.services.ml.contracts_frame``): contract_id, entity_id, supplier_id, date,
    days_to_fy_end, fiscal_year, amount_cad, award_type, n_bidders, first_seen."""
    out = df.copy().reset_index(drop=True)
    out["amount_cad"] = pd.to_numeric(out["amount_cad"], errors="coerce").astype(float)
    out["date"] = pd.to_datetime(out["date"])
    out["first_seen"] = pd.to_datetime(out["first_seen"])
    out["supplier_age_days"] = (out["date"] - out["first_seen"]).dt.days.clip(lower=0)
    entity_total = out.groupby("entity_id")["amount_cad"].transform("sum")
    out["entity_share"] = out["amount_cad"] / entity_total.where(entity_total > 0)

    # Days since the previous contract of the same entity → supplier pair (365 = none).
    out = out.sort_values(["entity_id", "supplier_id", "date", "contract_id"]).reset_index(
        drop=True
    )
    previous = out.groupby(["entity_id", "supplier_id"])["date"].shift(1)
    out["days_between_contracts"] = (out["date"] - previous).dt.days.clip(upper=365).fillna(365)

    thresholds = _thresholds_cad(out, jurisdiction, fx)
    amount = out["amount_cad"].to_numpy(dtype=float)
    gap = (thresholds - amount[:, None]) / thresholds
    gap = np.where((gap > 0) & np.isfinite(gap), gap, np.inf).min(axis=1)
    out["gap_to_threshold"] = np.minimum(gap, 1.0)
    out["_under"] = gap <= UNDER_BAND
    out["_thresholds"] = list(thresholds)
    return out


def _split_contracts(f: pd.DataFrame) -> np.ndarray:
    """Same entity and supplier, ≥ 2 contracts within 7 days, each below a threshold whose
    value their sum reaches — the classic way to avoid a competitive process."""
    flag = np.zeros(len(f), dtype=bool)
    days = (f["date"] - pd.Timestamp("1970-01-01")).dt.days.to_numpy()
    amount = f["amount_cad"].to_numpy(dtype=float)
    for idx in f.groupby(["entity_id", "supplier_id"]).indices.values():
        if len(idx) < 2:
            continue
        d, a = days[idx], amount[idx]
        for k, i in enumerate(idx):
            near = np.abs(d - d[k]) <= SPLIT_DAYS
            if near.sum() < 2:
                continue
            total = a[near].sum()
            for t in f.at[i, "_thresholds"]:
                if np.isfinite(t) and (a[near] < t).all() and total >= t:
                    flag[i] = True
                    break
    return flag


def _fy_end_spike(f: pd.DataFrame) -> np.ndarray:
    """Signed in the last 30 days of the fiscal year by an entity whose spend in that window
    is at least twice its average 30-day spend of the year (≥ 10 contracts that year)."""
    near_end = f["days_to_fy_end"].between(0, FY_END_DAYS - 1)
    keys = ["entity_id", "fiscal_year"]
    total = f.groupby(keys)["amount_cad"].transform("sum")
    count = f.groupby(keys)["amount_cad"].transform("count")
    window = f["amount_cad"].where(near_end, 0.0).groupby([f[k] for k in keys]).transform("sum")
    expected = total * FY_END_DAYS / 365
    return (near_end & (count >= 10) & (window >= FY_SPIKE_RATIO * expected)).to_numpy()


def apply_rules(f: pd.DataFrame) -> pd.DataFrame:
    large = f["amount_cad"].quantile(LARGE_QUANTILE)
    history_start = f["date"].min() + pd.Timedelta(days=365)
    bidders = pd.to_numeric(f["n_bidders"], errors="coerce")
    flags = pd.DataFrame(
        {
            "split_contract": _split_contracts(f),
            "under_threshold": f["_under"].to_numpy(),
            "single_bidder": (
                (bidders == 1) & f["award_type"].isin(["open", "limited"])
            ).to_numpy(),
            "fy_end_spike": _fy_end_spike(f),
            "new_large_supplier": (
                (f["supplier_age_days"] <= NEW_SUPPLIER_DAYS)
                & (f["amount_cad"] >= large)
                & (f["date"] >= history_start)
            ).to_numpy(),
        }
    )
    return flags.fillna(False).astype(bool)


def _matrix(f: pd.DataFrame, used: list[str]) -> np.ndarray:
    cols = []
    for name in used:
        col = pd.to_numeric(f[name], errors="coerce").astype(float)
        if name == "amount_cad":
            col = np.log10(col.clip(lower=1.0))
        cols.append(col.fillna(col.median()).to_numpy())
    return np.column_stack(cols)


def run(df: pd.DataFrame, params: RedFlagParams, fx: FxTable) -> dict[str, Any]:
    """Score, rank and explain. Deterministic for a given input (fixed seed, stable sort)."""
    f = build_features(df[df["amount_cad"] > 0].dropna(subset=["date"]), params.jurisdiction, fx)
    f = f.sort_values("contract_id").reset_index(drop=True)
    rules = apply_rules(f)
    # A feature with no information in this dataset (e.g. no bid counts) is left out.
    used = [n for n in FEATURES if pd.to_numeric(f[n], errors="coerce").nunique(dropna=True) > 1]
    x = _matrix(f, used)
    from sklearn.ensemble import IsolationForest  # lazy: ~85 MB, only when a model runs

    model = IsolationForest(
        n_estimators=N_TREES, contamination=params.contamination, random_state=SEED, n_jobs=1
    ).fit(x)
    raw = -model.score_samples(x)  # higher = more isolated
    lo, hi = float(raw.min()), float(raw.max())
    scale = (hi - lo) or 1.0
    anomaly = (raw - lo) / scale
    percentile = pd.Series(raw).rank(pct=True, method="average").to_numpy()

    hits = rules.to_numpy().sum(axis=1)
    score = 0.6 * percentile + 0.4 * np.minimum(hits, 2) / 2
    unusual = percentile >= UNUSUAL_PERCENTILE
    flagged = (hits >= 2) | unusual | ((hits >= 1) & (percentile >= 0.9))

    order = np.lexsort((f["contract_id"].to_numpy(), -np.round(score, 9)))
    top = [i for i in order if flagged[i]][: params.top_n]

    rng = np.random.default_rng(SEED)
    background = x[rng.choice(len(x), size=min(BACKGROUND, len(x)), replace=False)]
    explained = top[:EXPLAINED]
    contrib, base = (
        shapley_values(lambda m: -model.score_samples(m), x[explained], background)
        if explained
        else (np.zeros((0, len(used))), 0.0)
    )

    items = []
    for rank, i in enumerate(top, start=1):
        reasons = [r for r in RULES if rules.at[i, r]] + (["unusual_pattern"] if unusual[i] else [])
        row = f.iloc[i]
        item: dict[str, Any] = {
            "rank": rank,
            "contract_id": row["contract_id"],
            "entity_id": row["entity_id"],
            "entity_name": row.get("entity_name"),
            "supplier_id": row["supplier_id"],
            "supplier_name": row.get("supplier_name"),
            "signed_date": row["date"].date().isoformat(),
            "amount_cad": round(float(row["amount_cad"]), 2),
            "score": round(float(score[i]), 4),
            "anomaly": round(float(anomaly[i]), 4),
            "reasons": reasons,
            "facts": {
                "days_between_contracts": int(row["days_between_contracts"]),
                "supplier_age_days": None
                if pd.isna(row["supplier_age_days"])
                else int(row["supplier_age_days"]),
                "days_to_fy_end": None
                if pd.isna(row["days_to_fy_end"])
                else int(row["days_to_fy_end"]),
                "n_bidders": None if pd.isna(row["n_bidders"]) else int(row["n_bidders"]),
            },
        }
        if rank <= len(explained):
            item["contributions"] = sorted(
                (
                    {"feature": name, "value": round(float(v) / scale, 4)}
                    for name, v in zip(used, contrib[rank - 1], strict=True)
                ),
                key=lambda c: -abs(c["value"]),
            )
            item["base_value"] = round((base - lo) / scale, 4)
        items.append(item)

    return {
        "model": "isolation_forest+rules",
        "seed": SEED,
        "n_estimators": N_TREES,
        "contamination": params.contamination,
        "jurisdiction": params.jurisdiction,
        "features": used,
        "features_dropped": [n for n in FEATURES if n not in used],
        "rules": list(RULES),
        "thresholds": {
            "currency": THRESHOLDS.get(params.jurisdiction, THRESHOLDS["CA"])[0],
            "values": list(THRESHOLDS.get(params.jurisdiction, THRESHOLDS["CA"])[1]),
        },
        "contracts": len(f),
        "flagged": int(flagged.sum()),
        "rule_counts": {r: int(rules[r].sum()) for r in RULES},
        "unusual": int(unusual.sum()),
        "items": items,
    }
