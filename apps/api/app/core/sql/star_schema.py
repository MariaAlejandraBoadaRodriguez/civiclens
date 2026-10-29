"""Build the star schema (ADR-0006) from a cleaned dataset and store it as a DuckDB file.

fact_contract(contract_id, entity_id, supplier_id, date_id, category_id, amount_original,
currency, amount_cad, award_type, n_bidders, is_outlier) + dim_entity, dim_supplier,
dim_date, dim_category, dim_currency. Pure pandas until ``write_duckdb``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import duckdb
import pandas as pd

from app.core.cleaning.ops import FxTable, _as_dates, _as_numbers, _strings
from app.core.ingest.locale_parse import normalize_token

# Fiscal year: Colombia uses the calendar year ("vigencia"); Canada and Québec run April → March.
FISCAL_START_MONTH = {"CO": 1, "CA": 4, "QC": 4}

# contract_type / commodity type values (EN/FR/ES sources) → canonical category group.
CATEGORY_GROUPS = {
    "prestacion de servicios": "services",
    "servicios profesionales": "services",
    "consultoria": "services",
    "interventoria": "services",
    "suministros": "goods",
    "compraventa": "goods",
    "arrendamiento de inmuebles": "services",
    "obra": "construction",
    "s": "services",
    "g": "goods",
    "c": "construction",
    "services": "services",
    "services professionnels": "services",
    "approvisionnement (biens)": "goods",
    "goods": "goods",
    "biens": "goods",
    "travaux de construction": "construction",
    "works": "construction",
    "travaux": "construction",
}
GROUPS = ("goods", "services", "construction", "other")

TABLES = ("fact_contract", "dim_entity", "dim_supplier", "dim_date", "dim_category", "dim_currency")


@dataclass
class StarSchema:
    fact_contract: pd.DataFrame
    dim_entity: pd.DataFrame
    dim_supplier: pd.DataFrame
    dim_date: pd.DataFrame
    dim_category: pd.DataFrame
    dim_currency: pd.DataFrame

    def tables(self) -> dict[str, pd.DataFrame]:
        return {name: getattr(self, name) for name in TABLES}


def _key(prefix: str, value: object) -> str:
    return f"{prefix}-" + hashlib.sha1(normalize_token(value).encode()).hexdigest()[:10]  # noqa: S324


def _col(df: pd.DataFrame, name: str) -> list[object]:
    return _strings(df[name]) if name in df.columns else [None] * len(df)


def fiscal_year(d: date, jurisdiction: str) -> int:
    """Fiscal year labelled by the calendar year it ends in (FY2025 = Apr 2024 – Mar 2025)."""
    start = FISCAL_START_MONTH.get(jurisdiction, 1)
    return d.year if start == 1 or d.month < start else d.year + 1


def fiscal_year_end(fy: int, jurisdiction: str) -> date:
    """Last day of the fiscal year: 31 Dec (Colombia) or 31 Mar (Canada, Québec)."""
    return date(fy, 12, 31) if FISCAL_START_MONTH.get(jurisdiction, 1) == 1 else date(fy, 3, 31)


def category_group(value: object) -> str:
    if value is None:
        return "other"
    return CATEGORY_GROUPS.get(normalize_token(value), "other")


def build_star(
    clean: pd.DataFrame,
    jurisdiction: str,
    fx: FxTable,
    group_labels: dict[str, dict[str, str]],
    default_currency: str | None = None,
) -> StarSchema:
    """``group_labels`` = {group: {"en": ..., "es": ...}} from the API catalogs."""
    n = len(clean)
    dates = _as_dates(clean["signed_date"]) if "signed_date" in clean.columns else [None] * n
    # Parquet may hold tz-aware timestamps next to naive ones: dates are calendar days here.
    dates = [d.replace(tzinfo=None) if d is not None and d.tzinfo else d for d in dates]
    amounts = (
        _as_numbers(clean["amount_original"]) if "amount_original" in clean.columns else [None] * n
    )
    currencies = (
        [(str(c).strip().upper() if c else default_currency) for c in _col(clean, "currency")]
        if "currency" in clean.columns
        else [default_currency] * n
    )

    # --- entities
    entity_names = _col(clean, "entity_name")
    entity_ids = [
        str(e) if e is not None else _key("E", name)
        for e, name in zip(_col(clean, "entity_id"), entity_names, strict=True)
    ]
    dim_entity = (
        pd.DataFrame(
            {
                "entity_id": entity_ids,
                "entity_name": entity_names,
                "region": _col(clean, "region"),
                "city": _col(clean, "city"),
            }
        )
        .drop_duplicates("entity_id")
        .assign(jurisdiction=jurisdiction)
        .sort_values("entity_id")
        .reset_index(drop=True)
    )

    # --- suppliers (key: id when published, else a hash of the normalized name)
    supplier_names = _col(clean, "supplier_name")
    supplier_ids = [
        str(s) if s is not None else _key("S", name)
        for s, name in zip(_col(clean, "supplier_id"), supplier_names, strict=True)
    ]
    sup = pd.DataFrame(
        {
            "supplier_id": supplier_ids,
            "supplier_name": supplier_names,
            "d": [d.date() if d else None for d in dates],
        }
    )
    first_seen = sup.dropna(subset=["d"]).groupby("supplier_id")["d"].min()
    dim_supplier = sup.drop_duplicates("supplier_id")[["supplier_id", "supplier_name"]].reset_index(
        drop=True
    )
    dim_supplier["first_seen"] = dim_supplier["supplier_id"].map(first_seen)
    dim_supplier = dim_supplier.sort_values("supplier_id").reset_index(drop=True)

    # --- dates
    day = [d.date() if isinstance(d, datetime) else None for d in dates]
    date_ids = [int(d.strftime("%Y%m%d")) if d else None for d in day]
    uniq = sorted({d for d in day if d})
    dim_date = pd.DataFrame(
        {
            "date_id": [int(d.strftime("%Y%m%d")) for d in uniq],
            "date": uniq,
            "year": [d.year for d in uniq],
            "quarter": [(d.month - 1) // 3 + 1 for d in uniq],
            "month": [d.month for d in uniq],
            "month_start": [date(d.year, d.month, 1) for d in uniq],
            "fiscal_year": [fiscal_year(d, jurisdiction) for d in uniq],
            "days_to_fy_end": [
                (fiscal_year_end(fiscal_year(d, jurisdiction), jurisdiction) - d).days for d in uniq
            ],
        }
    )

    # --- categories
    sources = _col(clean, "contract_type")
    codes = _col(clean, "category_code")
    groups = [category_group(s) for s in sources]
    dim_category = pd.DataFrame(
        {
            "category_id": list(GROUPS),
            "code": list(GROUPS),
            "label_en": [group_labels[g]["en"] for g in GROUPS],
            "label_es": [group_labels[g]["es"] for g in GROUPS],
            "label_source": [
                ", ".join(
                    sorted(
                        {str(s) for s, g2 in zip(sources, groups, strict=True) if s and g2 == g}
                    )[:5]
                )
                or None
                for g in GROUPS
            ],
        }
    )

    # --- amounts in CAD (rate of the signed month)
    amount_cad = []
    for a, c, d in zip(amounts, currencies, dates, strict=True):
        if a is None or c is None:
            amount_cad.append(None)
        elif c == "CAD":
            amount_cad.append(round(a, 2))
        else:
            v = fx.convert(a, c, "CAD", f"{d.year:04d}-{d.month:02d}" if d else "")
            amount_cad.append(None if v is None else round(v, 2))

    contract_ids = [
        str(c) if c is not None else f"row-{i}" for i, c in enumerate(_col(clean, "contract_id"))
    ]
    if len(set(contract_ids)) < len(contract_ids):  # ids unique only within an entity (Canada)
        contract_ids = [f"{e}:{c}" for e, c in zip(entity_ids, contract_ids, strict=True)]
    seen: dict[str, int] = {}
    unique_ids = []
    for c in contract_ids:  # remaining collisions (flagged duplicates kept by the user)
        seen[c] = seen.get(c, 0) + 1
        unique_ids.append(c if seen[c] == 1 else f"{c}#{seen[c]}")

    bidders = _as_numbers(clean["n_bidders"]) if "n_bidders" in clean.columns else [None] * n
    outlier = (
        clean["amount_original_outlier"].tolist()
        if "amount_original_outlier" in clean.columns
        else [False] * n
    )
    award = [
        a if a in ("direct", "open", "limited", "other") else None
        for a in _col(clean, "award_type")
    ]
    fact = pd.DataFrame(
        {
            "contract_id": unique_ids,
            "entity_id": entity_ids,
            "supplier_id": supplier_ids,
            "date_id": pd.array(date_ids, dtype="Int64"),
            "category_id": groups,
            "category_code": codes,
            "amount_original": pd.array(amounts, dtype="Float64"),
            "currency": currencies,
            "amount_cad": pd.array(amount_cad, dtype="Float64"),
            "award_type": award,
            "n_bidders": pd.array([None if b is None else int(b) for b in bidders], dtype="Int64"),
            "is_outlier": [bool(o) for o in outlier],
        }
    )

    used = sorted({c for c in currencies if c})
    latest = max((d for d in dates if d), default=None)
    month = f"{latest.year:04d}-{latest.month:02d}" if latest else ""
    dim_currency = pd.DataFrame(
        {
            "currency": used,
            "cad_per_unit": [fx.cad_per_unit(c, month) for c in used],
            "fx_month": [month] * len(used),
            "fx_source": [fx.sources.get(c, "") for c in used],
        }
    )
    return StarSchema(fact, dim_entity, dim_supplier, dim_date, dim_category, dim_currency)


def write_duckdb(star: StarSchema, path: Path) -> None:
    """Materialize every table in a DuckDB file (atomic replace)."""
    tmp = path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp))
    try:
        for name, df in star.tables().items():
            con.register("_df", df)
            con.execute(f"CREATE TABLE {name} AS SELECT * FROM _df")  # noqa: S608 — fixed table names
            con.unregister("_df")
    finally:
        con.close()
    tmp.replace(path)
