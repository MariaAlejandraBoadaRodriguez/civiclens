"""Models for any table (owner requirement: generic analysis is the core).

- ``target_model``: predicts a column the user picks. The task (classification or regression)
  follows from the target's kind. It uses a stratified 75/25 split and compares against a
  baseline (the majority class, or the mean), reports metrics and permutation importance,
  warns about leakage, and checks fairness across sensitive groups. Sensitive attributes are
  never model inputs.
- ``anomalies``: Isolation Forest on the quantities; each flagged row names the value that is
  most unusual (robust z-score).
- ``segments``: k-means on standardized quantities and the main categories, k chosen by
  silhouette; each segment is profiled by what sets it apart from the whole table.
- ``forecast``: the honest monthly forecast of ``app.core.ml.forecast`` on any date + quantity.

Pure functions on pandas frames read from the table ``data``. Large tables are sampled (fixed
seed) and the result says so, so a run fits in 512 MB. Results hold ids and numbers; texts
live in the API catalogs (``models.*``).
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

from app.core.analysis.table import NUMERIC_KINDS, TEMPORAL_KINDS, ColumnMeta
from app.core.ml import SEED

MAX_ROWS = 20_000  # rows used for training (sampled above this, and the card says so)
MAX_CATEGORIES = 60  # categories with more labels are left out as features
MAX_FEATURES = 40
IMPORTANCE_ROWS = 2_000
SILHOUETTE_ROWS = 1_500
WORKING_MEMORY_MB = 32  # sklearn chunked computations (pairwise distances)
LEAK_STRONG = 0.95  # one feature alone predicts the target almost perfectly
LEAK_HINTED = 0.75  # …or strongly, and its name says it is known only after the outcome
LEAK_HINT = re.compile(
    r"(^|_)(duration|length|outcome|result|status|paid|closed|final|after|post|end)($|_)"
)
SENSITIVE_HINT = {
    "age": re.compile(r"(^|_)(age|edad|age_years|birth|nacimiento)($|_)"),
    "sex": re.compile(r"(^|_)(sex|gender|sexo|genero|sexe|personal_status_sex)($|_)"),
    "marital_status": re.compile(r"(^|_)(marital|civil|estado_civil|marital_status)($|_)"),
    "nationality": re.compile(
        r"(^|_)(nationality|nacionalidad|foreign|foreign_worker|citizenship|race|ethnicity)($|_)"
    ),
}
FAIRNESS_RATIO = 0.8  # four-fifths rule on the rate of positive predictions
MIN_GROUP = 20


# --------------------------------------------------------------------------- features


def task_for(target: ColumnMeta) -> str | None:
    if target.binary or target.kind == "boolean":
        return "binary"
    if target.kind == "category" and 2 < target.distinct <= 20:
        return "multiclass"
    if target.kind in NUMERIC_KINDS and target.distinct > 2:
        return "regression"
    return None


def sensitive_columns(
    metas: list[ColumnMeta], roles: dict[str, str] | None = None
) -> dict[str, str]:
    """Sensitive attribute → column: the pack's mapped sensitive roles, else header hints."""
    out = dict(roles or {})
    for m in metas:
        for attr, hint in SENSITIVE_HINT.items():
            if attr not in out and m.name not in out.values() and hint.search(m.name):
                out[attr] = m.name
    return out


def feature_columns(metas: list[ColumnMeta], target: str, excluded: set[str]) -> list[ColumnMeta]:
    out = []
    for m in metas:
        if m.name == target or m.name in excluded or m.null_share > 0.6 or m.distinct < 2:
            continue
        if m.kind in NUMERIC_KINDS or m.kind == "boolean" or m.kind in TEMPORAL_KINDS:
            out.append(m)
        elif m.kind == "category" and m.distinct <= MAX_CATEGORIES:
            out.append(m)
    return out[:MAX_FEATURES]


def encode(frame: pd.DataFrame, features: list[ColumnMeta]) -> tuple[pd.DataFrame, list[str]]:
    """Numbers stay numbers (NaN allowed), dates become year + month, flags 0/1, categories
    integer codes (the boosting model treats them as categorical)."""
    cols: dict[str, pd.Series] = {}
    categorical: list[str] = []
    for m in features:
        s = frame[m.name]
        if m.kind in TEMPORAL_KINDS:
            d = pd.to_datetime(s, errors="coerce")
            cols[f"{m.name}__year"] = d.dt.year.astype("float64")
            cols[f"{m.name}__month"] = d.dt.month.astype("float64")
        elif m.kind == "boolean":
            cols[m.name] = s.astype("float64")
        elif m.kind == "category":
            codes = pd.Categorical(s.astype("string")).codes.astype("float64")
            cols[m.name] = pd.Series(np.where(codes < 0, np.nan, codes), index=s.index)
            categorical.append(m.name)
        else:
            cols[m.name] = pd.to_numeric(s, errors="coerce").astype("float64")
    return pd.DataFrame(cols, index=frame.index), categorical


def labels(values: pd.Series) -> pd.Series:
    """Values as text the way the table shows them: whole numbers without ".0"."""
    if pd.api.types.is_numeric_dtype(values) and not pd.api.types.is_bool_dtype(values):
        whole = values.dropna()
        if len(whole) and (whole % 1 == 0).all():
            return values.astype("Int64").astype("string")
    return values.astype("string")


def source_of(column: str) -> str:
    """Encoded column → the ``data`` column it comes from."""
    return column.split("__")[0]


def sample(frame: pd.DataFrame, n: int, stratify: pd.Series | None = None) -> pd.DataFrame:
    if len(frame) <= n:
        return frame
    if stratify is None:
        return frame.sample(n=n, random_state=SEED)
    picked = stratify.groupby(stratify, observed=True).sample(
        frac=n / len(frame), random_state=SEED
    )
    return frame.loc[picked.index]


# --------------------------------------------------------------------------- target model


def _target_values(frame: pd.DataFrame, target: ColumnMeta, task: str, positive: str | None):
    s = frame[target.name]
    if task == "regression":
        return pd.to_numeric(s, errors="coerce").astype("float64")
    text = s.astype("string")
    if task == "binary":
        if positive is None:
            values = text.dropna().value_counts()
            words = [v for v in values.index if str(v).lower() in ("true", "yes", "1", "si", "sí")]
            positive = words[0] if words else str(values.index[-1])  # yes-like, else minority
        return (text == str(positive)).astype("float64").where(text.notna()), str(positive)
    return text


def _single_feature_strength(x: pd.Series, y: pd.Series, task: str) -> float:
    """How well one feature alone predicts the target: AUC (binary, symmetric), else |r|
    on ranks. Used for leakage warnings only."""
    from sklearn.metrics import roc_auc_score

    ok = x.notna() & y.notna()
    if ok.sum() < 30 or x[ok].nunique() < 2:
        return 0.0
    if task == "binary":
        if y[ok].nunique() < 2:
            return 0.0
        auc = roc_auc_score(y[ok], x[ok])
        return float(max(auc, 1 - auc))
    if task == "regression":
        return float(abs(x[ok].rank().corr(y[ok].rank())))
    return 0.0


def target_model(
    frame: pd.DataFrame,
    metas: list[ColumnMeta],
    target: str,
    positive: str | None = None,
    sensitive_roles: dict[str, str] | None = None,
) -> dict[str, Any]:
    from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
    from sklearn.inspection import permutation_importance
    from sklearn.model_selection import train_test_split

    by_name = {m.name: m for m in metas}
    meta = by_name[target]
    task = task_for(meta)
    if task is None:
        return {"status": "unsupported_target", "target": target, "target_kind": meta.kind}
    sensitive = sensitive_columns(metas, sensitive_roles)
    features = feature_columns(metas, target, set(sensitive.values()))
    if not features:
        return {"status": "no_features", "target": target}

    data = frame[frame[target].notna()]
    rows_total = len(data)
    if task == "binary":
        y_all, positive = _target_values(data, meta, task, positive)
    else:
        y_all = _target_values(data, meta, task, positive)
    data = data.assign(__y=y_all).dropna(subset=["__y"])
    if task == "multiclass":  # rare classes cannot be split or learned: group them
        counts = data["__y"].value_counts()
        rare = counts[counts < 10].index
        data = data.assign(__y=data["__y"].where(~data["__y"].isin(rare), "__other__"))
    sampled = len(data) > MAX_ROWS
    data = sample(data, MAX_ROWS, data["__y"] if task != "regression" else None)
    x, categorical = encode(data, features)
    y = data["__y"]
    if task != "regression" and y.nunique() < 2:
        return {"status": "single_class", "target": target}

    strat = y if task != "regression" else None
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=0.25, random_state=SEED, stratify=strat
    )
    cat_mask = [c in categorical for c in x.columns]
    params = {
        "max_iter": 200,
        "learning_rate": 0.08,
        "random_state": SEED,
        "categorical_features": cat_mask,
    }
    if task == "regression":
        model = HistGradientBoostingRegressor(**params).fit(x_train, y_train)
    else:
        model = HistGradientBoostingClassifier(**params).fit(x_train, y_train)

    metrics, baseline, threshold = _metrics(task, model, x_test, y_test, y_train)

    idx = x_test.index[: min(IMPORTANCE_ROWS, len(x_test))]
    scoring = {"binary": "roc_auc", "multiclass": "accuracy", "regression": "r2"}[task]
    perm = permutation_importance(
        model,
        x_test.loc[idx],
        y_test.loc[idx],
        scoring=scoring,
        n_repeats=3,
        random_state=SEED,
    )
    grouped: dict[str, float] = {}
    for col, value in zip(x.columns, perm.importances_mean, strict=True):
        grouped[source_of(col)] = grouped.get(source_of(col), 0.0) + max(float(value), 0.0)
    total = sum(grouped.values()) or 1.0
    importance = sorted(
        (
            {"feature": f, "importance": round(v, 4), "share": round(v / total, 4)}
            for f, v in grouped.items()
        ),
        key=lambda r: -r["importance"],
    )[:12]

    leakage = []
    for m in features:
        enc = [c for c in x.columns if source_of(c) == m.name]
        strength = max(
            _single_feature_strength(x[c], y.astype("float64") if task != "multiclass" else y, task)
            for c in enc
        )
        hinted = bool(LEAK_HINT.search(m.name))
        top = importance and importance[0]["feature"] == m.name and importance[0]["share"] > 0.5
        if strength >= LEAK_STRONG or (hinted and (strength >= LEAK_HINTED or top)):
            leakage.append(
                {
                    "feature": m.name,
                    "strength": round(strength, 3),
                    "reason": "name_and_strength" if hinted else "too_strong",
                }
            )

    fairness = []
    if task == "binary":
        test_rows = data.loc[x_test.index]
        predicted = model.predict_proba(x_test)[:, 1] >= threshold
        for attr, col in sensitive.items():
            if col in test_rows.columns:
                fairness.append(
                    _fairness(
                        attr, col, by_name.get(col), test_rows[col], y_test.to_numpy(), predicted
                    )
                )

    return {
        "status": "ok",
        "task": task,
        "target": target,
        "positive": positive,
        "model": "hist_gradient_boosting",
        "baseline": {
            "binary": "majority_class",
            "multiclass": "majority_class",
            "regression": "mean",
        }[task],
        "seed": SEED,
        "rows": rows_total,
        "rows_used": int(len(data)),
        "sampled": sampled,
        "train_rows": int(len(x_train)),
        "test_rows": int(len(x_test)),
        "features": [m.name for m in features],
        "excluded_sensitive": sorted(sensitive.values()),
        "metrics": metrics,
        "baseline_metrics": baseline,
        "beats_baseline": bool(_beats(task, metrics, baseline)),
        "importance": importance,
        "leakage": leakage,
        "fairness": [f for f in fairness if f["groups"]],
    }


def _metrics(task, model, x_test, y_test, y_train):
    from sklearn.metrics import (
        accuracy_score,
        average_precision_score,
        f1_score,
        mean_absolute_error,
        precision_score,
        r2_score,
        recall_score,
        roc_auc_score,
    )

    if task == "regression":
        pred = model.predict(x_test)
        base = np.full(len(y_test), float(y_train.mean()))
        rmse = float(np.sqrt(np.mean((y_test - pred) ** 2)))
        return (
            {
                "mae": round(float(mean_absolute_error(y_test, pred)), 4),
                "rmse": round(rmse, 4),
                "r2": round(float(r2_score(y_test, pred)), 4),
            },
            {
                "mae": round(float(mean_absolute_error(y_test, base)), 4),
                "r2": round(float(r2_score(y_test, base)), 4),
            },
            None,
        )
    if task == "multiclass":
        pred = model.predict(x_test)
        majority = y_train.value_counts().index[0]
        return (
            {
                "accuracy": round(float(accuracy_score(y_test, pred)), 4),
                "f1_macro": round(float(f1_score(y_test, pred, average="macro")), 4),
            },
            {"accuracy": round(float((y_test == majority).mean()), 4)},
            None,
        )
    proba = model.predict_proba(x_test)[:, 1]
    prevalence = float(y_train.mean())
    # Flag the share of rows the training data says are positive: comparable across groups
    # and not 0.5, which flags nobody when positives are rare.
    threshold = float(np.quantile(proba, 1 - prevalence)) if 0 < prevalence < 1 else 0.5
    pred = proba >= threshold
    majority = float(max(prevalence, 1 - prevalence))
    return (
        {
            "roc_auc": round(float(roc_auc_score(y_test, proba)), 4),
            "average_precision": round(float(average_precision_score(y_test, proba)), 4),
            "accuracy": round(float(accuracy_score(y_test, pred)), 4),
            "precision": round(float(precision_score(y_test, pred, zero_division=0)), 4),
            "recall": round(float(recall_score(y_test, pred, zero_division=0)), 4),
            "threshold": round(threshold, 4),
            "positive_rate": round(prevalence, 4),
        },
        {"roc_auc": 0.5, "accuracy": round(majority, 4), "average_precision": round(prevalence, 4)},
        threshold,
    )


def _beats(task: str, metrics: dict[str, float], baseline: dict[str, float]) -> bool:
    if task == "binary":
        return (
            metrics["roc_auc"] > 0.55
            and metrics["average_precision"] > baseline["average_precision"]
        )
    if task == "multiclass":
        return metrics["accuracy"] > baseline["accuracy"]
    return metrics["mae"] < baseline["mae"]


def _groups(values: pd.Series, meta: ColumnMeta | None) -> pd.Series:
    if meta is not None and meta.kind in NUMERIC_KINDS and meta.distinct > 12:
        bins = [-np.inf, 25, 35, 50, 65, np.inf]
        bands = ["<25", "25-34", "35-49", "50-64", "65+"]
        return pd.cut(
            pd.to_numeric(values, errors="coerce"), bins=bins, labels=bands, right=False
        ).astype("string")
    return labels(values)


def _fairness(attr, col, meta, values, actual, predicted) -> dict[str, Any]:
    groups = _groups(values, meta)
    out = []
    for g in groups.dropna().unique():
        mask = (groups == g).fillna(False).to_numpy(dtype=bool)
        if mask.sum() < MIN_GROUP:
            continue
        a, p = actual[mask], predicted[mask]
        positives, negatives = a == 1, a == 0
        out.append(
            {
                "group": str(g),
                "rows": int(mask.sum()),
                "actual_rate": round(float(a.mean()), 4),
                "flagged_rate": round(float(p.mean()), 4),
                "true_positive_rate": round(float(p[positives].mean()), 4)
                if positives.any()
                else None,
                "false_positive_rate": round(float(p[negatives].mean()), 4)
                if negatives.any()
                else None,
            }
        )
    out.sort(key=lambda r: -r["rows"])
    rates = [g["flagged_rate"] for g in out]
    ratio = (min(rates) / max(rates)) if rates and max(rates) > 0 else None
    return {
        "attribute": attr,
        "column": col,
        "groups": out[:8],
        "disparity_ratio": None if ratio is None else round(ratio, 3),
        "passes": ratio is None or ratio >= FAIRNESS_RATIO,
    }


# --------------------------------------------------------------------------- anomalies


def _numbers(metas: list[ColumnMeta]) -> list[ColumnMeta]:
    from app.core.analysis.questions import year_like

    return [
        m
        for m in metas
        if m.kind in NUMERIC_KINDS
        and not m.binary
        and m.distinct > 2
        and m.null_share < 0.5
        and not year_like(m)
    ][:15]


def anomalies(frame: pd.DataFrame, metas: list[ColumnMeta], top: int = 20) -> dict[str, Any]:
    from sklearn.ensemble import IsolationForest

    nums = _numbers(metas)
    if not nums:
        return {"status": "no_numbers"}
    cols = [m.name for m in nums]
    data = sample(frame, MAX_ROWS * 2)
    x = data[cols].apply(pd.to_numeric, errors="coerce").astype("float64")
    x = x.fillna(x.median())
    forest = IsolationForest(n_estimators=150, contamination="auto", random_state=SEED)
    score = -forest.fit(x).score_samples(x)  # higher = more unusual
    flagged = forest.predict(x) == -1
    median = x.median()
    mad = (x - median).abs().median().replace(0, np.nan)
    z = ((x - median) / (1.4826 * mad)).fillna(0.0)
    order = np.argsort(-score)[:top]
    keep = [m.name for m in metas if m.kind in ("identifier", "category")][:2]
    shown = {k: labels(data[k]).astype(object).where(data[k].notna(), None) for k in keep}
    rows = []
    for i in order:
        zi = z.iloc[i]
        feature = str(zi.abs().idxmax())
        rows.append(
            {
                "row": int(data.index[i]) + 1,
                "score": round(float(score[i]), 4),
                "feature": feature,
                "value": None if pd.isna(x.iloc[i][feature]) else float(x.iloc[i][feature]),
                "median": float(median[feature]),
                "z": round(float(zi[feature]), 2),
                "labels": {k: shown[k].iloc[i] for k in keep},
            }
        )
    return {
        "status": "ok",
        "model": "isolation_forest",
        "seed": SEED,
        "rows": int(len(frame)),
        "rows_used": int(len(data)),
        "sampled": len(data) < len(frame),
        "features": cols,
        "flagged": int(flagged.sum()),
        "flagged_share": round(float(flagged.mean()), 4),
        "top": rows,
    }


# --------------------------------------------------------------------------- segments


def segments(frame: pd.DataFrame, metas: list[ColumnMeta]) -> dict[str, Any]:
    from sklearn import config_context
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    nums = _numbers(metas)[:8]
    cats = [
        m for m in metas if m.kind == "category" and 2 <= m.distinct <= 12 and m.null_share < 0.5
    ][:4]
    if not nums and not cats:
        return {"status": "no_features"}
    data = sample(frame, MAX_ROWS)
    parts = []
    if nums:
        x = data[[m.name for m in nums]].apply(pd.to_numeric, errors="coerce").astype("float64")
        x = x.fillna(x.median())
        q1, q3 = x.quantile(0.05), x.quantile(0.95)
        x = x.clip(q1, q3, axis=1)
        std = x.std().replace(0, 1.0)
        parts.append((x - x.mean()) / std)
    for m in cats:
        parts.append(pd.get_dummies(labels(data[m.name]), prefix=m.name, dtype="float64") * 0.7)
    z = pd.concat(parts, axis=1).fillna(0.0).to_numpy()
    # Silhouette needs pairwise distances: score k on 1,500 rows with sklearn's working memory
    # capped (its 1 GB default alone would break the 512 MB budget).
    probe = z[np.random.default_rng(SEED).permutation(len(z))[:SILHOUETTE_ROWS]]
    best_k, best_s = 2, -1.0
    for k in range(2, 7):
        if len(probe) <= k:
            break
        assigned = KMeans(n_clusters=k, n_init=4, random_state=SEED).fit_predict(probe)
        if len(set(assigned)) < 2:
            continue
        with config_context(working_memory=WORKING_MEMORY_MB):
            s = float(silhouette_score(probe, assigned, random_state=SEED))
        if s > best_s + 0.01:
            best_k, best_s = k, s
    assigned = KMeans(n_clusters=best_k, n_init=4, random_state=SEED).fit_predict(z)

    out = []
    for k in range(best_k):
        mask = assigned == k
        seg = data[mask]
        traits = []
        for m in nums:
            overall = pd.to_numeric(data[m.name], errors="coerce").median()
            inside = pd.to_numeric(seg[m.name], errors="coerce").median()
            spread = pd.to_numeric(data[m.name], errors="coerce").std() or 1.0
            effect = (inside - overall) / spread
            if pd.notna(effect) and abs(effect) >= 0.3:
                traits.append(
                    {
                        "kind": "number",
                        "column": m.source,
                        "direction": "higher" if effect > 0 else "lower",
                        "median": float(inside),
                        "overall": float(overall),
                        "strength": round(abs(float(effect)), 3),
                    }
                )
        for m in cats:
            share_in = labels(seg[m.name]).value_counts(normalize=True)
            share_all = labels(data[m.name]).value_counts(normalize=True)
            if share_in.empty:
                continue
            value = share_in.index[0]
            lift = share_in.iloc[0] - share_all.get(value, 0.0)
            if lift >= 0.1:
                traits.append(
                    {
                        "kind": "category",
                        "column": m.source,
                        "value": str(value),
                        "share": round(float(share_in.iloc[0]), 4),
                        "overall": round(float(share_all.get(value, 0.0)), 4),
                        "strength": round(float(lift) * 2, 3),
                    }
                )
        traits.sort(key=lambda t: -t["strength"])
        out.append(
            {
                "segment": k + 1,
                "rows": int(mask.sum()),
                "share": round(float(mask.mean()), 4),
                "traits": traits[:4],
            }
        )
    out.sort(key=lambda s: -s["rows"])
    for i, s in enumerate(out, start=1):
        s["segment"] = i
    return {
        "status": "ok",
        "model": "kmeans",
        "seed": SEED,
        "k": best_k,
        "silhouette": round(best_s, 3),
        "rows": int(len(frame)),
        "rows_used": int(len(data)),
        "sampled": len(data) < len(frame),
        "features": [m.name for m in nums] + [m.name for m in cats],
        "segments": out,
    }


# --------------------------------------------------------------------------- forecast


def forecast_input(
    frame: pd.DataFrame, metas: list[ColumnMeta]
) -> tuple[pd.DataFrame, str | None, str | None] | None:
    """(date + value frame for ``forecast.run``, date column, metric column or None = rows)."""
    dates = [m for m in metas if m.kind in TEMPORAL_KINDS and m.distinct > 1]
    if not dates:
        return None
    from app.core.analysis.questions import pick

    date = dates[0]
    nums = [m for m in pick(metas).numbers if m.min is not None and float(m.min) >= 0]
    metric = nums[0] if nums else None
    values = (
        pd.to_numeric(frame[metric.name], errors="coerce")
        if metric is not None
        else pd.Series(1.0, index=frame.index)
    )
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(frame[date.name], errors="coerce"),
            "amount_cad": values.astype("float64"),
            "entity_id": None,
        }
    )
    return out.dropna(subset=["date"]), date.name, None if metric is None else metric.name
