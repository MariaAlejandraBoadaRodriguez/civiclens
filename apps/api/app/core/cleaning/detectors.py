"""Issue detectors: find data problems in a staged dataset and propose options.

Each issue carries machine data only (types, counts, recipe steps, previews, KPI values);
the API turns it into localized cards using ``issues.<issue_type>.*`` catalog keys
(ADR-0007). Detectors run in pipeline order and each later detector sees the data after
the *recommended* option of the earlier issues — previews are therefore exact for the
recommended path (the UI says so).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

from app.core.cleaning import kpis
from app.core.cleaning.ops import (
    AWARD_TYPES,
    CANONICAL_AWARD_TYPES,
    Context,
    _as_numbers,
    _outlier_bounds,
    _strings,
    apply_steps,
    is_text,
)
from app.core.ingest.locale_parse import (
    DateFormat,
    NumberLocale,
    classify_date,
    classify_number,
    infer_dayfirst,
    is_null_token,
    normalize_token,
    parse_date,
)

ROW_ID = "__row"
EXAMPLES = 3

Step = dict[str, Any]
Kpi = Callable[[pd.DataFrame], dict[str, Any]]


@dataclass
class Option:
    option_id: str
    steps: list[Step]
    recommended: bool = False
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class Issue:
    issue_id: str
    issue_type: str
    category: str  # quality dimension: completeness | uniqueness | validity | consistency
    field: str | None
    affected_rows: int
    params: dict[str, Any]
    options: list[Option]
    preview_columns: list[str] = field(default_factory=list)
    preview_before: list[list[Any]] = field(default_factory=list)
    preview_after: dict[str, list[list[Any]]] = field(default_factory=dict)
    kpi_id: str | None = None
    kpi_before: dict[str, Any] | None = None
    kpi_after: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def recommended(self) -> Option:
        return next((o for o in self.options if o.recommended), self.options[0])

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DetectContext:
    ctx: Context
    profile: dict[str, Any]
    default_currency: str | None

    def column_profile(self, name: str) -> dict[str, Any] | None:
        for c in self.profile.get("columns_profile", []):
            if (c["canonical_field"] or c["source_header"]) == name:
                return c
        return None


# --------------------------------------------------------------------------- helpers


def _cell(value: object) -> Any:
    """Preview cell as JSON: text stays text (as written), numbers stay numbers so the UI
    formats them in its own locale, dates become ISO strings."""
    if value is None or value is pd.NaT or (isinstance(value, float) and value != value):
        return None
    if isinstance(value, pd.Timestamp):
        if value.hour or value.minute or value.second:
            return value.isoformat(timespec="seconds")
        return value.date().isoformat()
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, int | float):
        return float(value) if isinstance(value, float) else int(value)
    if isinstance(value, str):
        return value
    if hasattr(value, "item"):  # numpy / pandas scalars
        return value.item()
    return str(value)


def _examples(df: pd.DataFrame, mask: list[bool], column: str | None) -> list[int]:
    """Row ids of up to 3 affected rows, preferring distinct values (deterministic)."""
    seen: set[object] = set()
    rows: list[int] = []
    values = _strings(df[column]) if column and column in df.columns else [None] * len(df)
    for row_id, hit, value in zip(df[ROW_ID].tolist(), mask, values, strict=True):
        if hit and value not in seen:
            seen.add(value)
            rows.append(row_id)
            if len(rows) == EXAMPLES:
                break
    return rows


def _snapshot(df: pd.DataFrame, rows: list[int], columns: list[str]) -> list[list[Any]]:
    """Values of ``columns`` for the given row ids; removed rows end with ``__removed__``."""
    index = {rid: i for i, rid in enumerate(df[ROW_ID].tolist())}
    out = []
    for rid in rows:
        if rid not in index:
            out.append([None] * len(columns) + ["__removed__"])
            continue
        i = index[rid]
        out.append([_cell(df[c].iat[i]) if c in df.columns else None for c in columns])
    return out


def _finish(
    issue: Issue,
    base: pd.DataFrame,
    dc: DetectContext,
    rows: list[int],
    columns: list[str],
    kpi: Kpi | None = None,
    kpi_id: str | None = None,
    kpi_before: dict[str, Any] | None = None,
) -> Issue:
    """Apply every option to the base data to build the Before/After preview and KPI."""
    issue.preview_columns = columns
    issue.preview_before = _snapshot(base, rows, columns)
    issue.kpi_id = kpi_id
    issue.kpi_before = kpi_before if kpi_before is not None else (kpi(base) if kpi else None)
    for option in issue.options:
        after = apply_steps(base, option.steps, dc.ctx)
        issue.preview_after[option.option_id] = _snapshot(after, rows, columns)
        if kpi:
            issue.kpi_after[option.option_id] = kpi(after)
    return issue


def _step(op: str, **args: Any) -> Step:
    return {"op": op, "args": args}


def _text_column(base: pd.DataFrame, col: str) -> bool:
    return col in base.columns and is_text(base[col])


# --------------------------------------------------------------------------- detectors


def detect_header_mapping(base: pd.DataFrame, dc: DetectContext) -> list[Issue]:
    """Low-confidence header matches from the profile (``needs_check``)."""
    issues = []
    for col in dc.profile.get("columns_profile", []):
        name, source = col["canonical_field"], col["source_header"]
        if not col.get("needs_check") or name not in base.columns:
            continue
        options = [
            Option("keep", [], recommended=True, params={"field": name}),
            Option("unmap", [_step("rename_columns", mapping={name: source})]),
        ]
        for alt in col.get("candidates", []):
            if alt != name and alt not in base.columns:
                options.append(
                    Option(
                        f"use_{alt}",
                        [_step("rename_columns", mapping={name: alt})],
                        params={"field": alt},
                    )
                )
        params = {"header": source, "field": name, "confidence": col["mapping_confidence"]}
        issues.append(
            Issue(
                f"header_mapping:{source}",
                "header_mapping",
                "validity",
                name,
                len(base),
                params,
                options,
            )
        )
    return issues


def detect_pii(base: pd.DataFrame, dc: DetectContext) -> list[Issue]:
    cols = [
        c["canonical_field"] or c["source_header"]
        for c in dc.profile.get("columns_profile", [])
        if c.get("pii_kind")
    ]
    cols = [c for c in cols if c in base.columns]
    if not cols:
        return []
    columns = list(zip(*(_strings(base[c]) for c in cols), strict=True))
    mask = [any(v not in (None, "") for v in row) for row in columns]
    options = [
        Option("mask", [_step("mask_columns", columns=cols)], recommended=True),
        Option("drop", [_step("drop_columns", columns=cols)]),
        Option("keep", []),
    ]
    params = {"columns": ", ".join(cols), "count": len(cols)}
    issue = Issue("pii", "pii", "validity", cols[0], sum(mask), params, options)
    return [_finish(issue, base, dc, _examples(base, mask, cols[0]), cols)]


def detect_duplicates(base: pd.DataFrame, dc: DetectContext) -> list[Issue]:
    data = [c for c in base.columns if c != ROW_ID]
    n_exact = int(base[data].astype(str).duplicated().sum())
    flagged = apply_steps(base, [_step("drop_duplicates", mode="near", keep="flag")], dc.ctx)
    mask = flagged["is_duplicate"].tolist()
    total = sum(mask)
    if total == 0:
        return []
    options = [
        Option(
            "keep_first", [_step("drop_duplicates", mode="near", keep="first")], recommended=True
        ),
        Option("keep_last", [_step("drop_duplicates", mode="near", keep="last")]),
        Option("flag", [_step("drop_duplicates", mode="near", keep="flag")]),
    ]
    params = {
        "total": total,
        "exact": n_exact,
        "near": total - n_exact,
        "share": round(total / len(base), 4),
    }
    issue = Issue("duplicates", "duplicates", "uniqueness", None, total, params, options)
    cols = [
        c
        for c in ("contract_id", "supplier_name", "amount_original", "signed_date")
        if c in base.columns
    ]
    rows = _examples(base, mask, cols[0] if cols else None)
    return [_finish(issue, base, dc, rows, cols, kpis.contract_count, "contract_count")]


def detect_missing(base: pd.DataFrame, dc: DetectContext) -> list[Issue]:
    """Missing values written as text (``N/A``, ``sin dato``, ``non disponible``…)."""
    tokens: Counter[str] = Counter()
    per_column: Counter[str] = Counter()
    mask = [False] * len(base)
    for col in base.columns:
        if col == ROW_ID or not is_text(base[col]):
            continue
        for i, v in enumerate(_strings(base[col])):
            if v is not None and str(v).strip() and is_null_token(v):
                tokens[str(v)] += 1
                per_column[col] += 1
                mask[i] = True
    if not tokens:
        return []
    options = [
        Option("to_null", [_step("standardize_nulls")], recommended=True),
        Option("keep", []),
    ]
    top = [t for t, _ in tokens.most_common(5)]
    params = {
        "tokens": ", ".join(f"“{t}”" for t in top),
        "cells": sum(tokens.values()),
        "variants": len(tokens),
        "columns": len(per_column),
    }
    issue = Issue(
        "missing_values", "missing_values", "completeness", None, sum(mask), params, options
    )
    col = per_column.most_common(1)[0][0]
    col_mask = [
        v is not None and bool(str(v).strip()) and is_null_token(v) for v in _strings(base[col])
    ]
    return [_finish(issue, base, dc, _examples(base, col_mask, col), [col])]


def detect_time_zone(base: pd.DataFrame, dc: DetectContext) -> list[Issue]:
    col = "signed_date"
    if not _text_column(base, col):
        return []
    mask = [
        isinstance(v, str) and (d := parse_date(v)) is not None and d.tzinfo is not None
        for v in _strings(base[col])
    ]
    if not any(mask):
        return []
    options = [
        Option("to_utc", [_step("normalize_timezones", column=col, to="utc")], recommended=True),
        Option("local", [_step("normalize_timezones", column=col, to="local")]),
    ]
    issue = Issue(
        f"time_zone:{col}",
        "time_zone",
        "consistency",
        col,
        sum(mask),
        {"count": sum(mask)},
        options,
    )
    return [_finish(issue, base, dc, _examples(base, mask, col), [col])]


def detect_date_format(base: pd.DataFrame, dc: DetectContext) -> list[Issue]:
    col = "signed_date"
    if not _text_column(base, col):
        return []
    values = _strings(base[col])
    formats = [classify_date(v) for v in values]
    counts = Counter(f for f in formats if f is not None)
    if not counts:
        return []
    dominant = counts.most_common(1)[0][0]
    mask = [f is not None and f != dominant for f in formats]
    dayfirst = infer_dayfirst(values)
    options = [
        Option(
            "day_first", [_step("parse_dates", column=col, dayfirst=True)], recommended=dayfirst
        ),
        Option(
            "month_first",
            [_step("parse_dates", column=col, dayfirst=False)],
            recommended=not dayfirst,
        ),
    ]
    params = {
        "formats": len(counts),
        "iso": counts.get(DateFormat.ISO, 0),
        "dmy": counts.get(DateFormat.DMY, 0),
        "mdy": counts.get(DateFormat.MDY, 0),
        "ambiguous": counts.get(DateFormat.AMBIGUOUS, 0),
    }
    issue = Issue(
        f"date_format:{col}", "date_format", "consistency", col, sum(mask), params, options
    )
    return [
        _finish(
            issue,
            base,
            dc,
            _examples(base, mask, col),
            [col],
            lambda d: kpis.readable_dates(d, strict=False),
            "readable_dates",
            kpi_before=kpis.readable_dates(base, strict=True),
        )
    ]


def detect_number_locale(base: pd.DataFrame, dc: DetectContext) -> list[Issue]:
    """Amounts stored as text, possibly in several notations (``1.234,56`` / ``1,234.56``)."""
    col = "amount_original"
    if not _text_column(base, col):
        return []
    kinds = [None if v is None else classify_number(str(v)) for v in _strings(base[col])]
    counts = Counter(k for k in kinds if k in (NumberLocale.COMMA, NumberLocale.POINT))
    comma, point = counts.get(NumberLocale.COMMA, 0), counts.get(NumberLocale.POINT, 0)
    if comma and point:
        minority = NumberLocale.POINT if comma >= point else NumberLocale.COMMA
        mask = [k == minority for k in kinds]
    else:
        mask = [k == NumberLocale.COMMA for k in kinds]
    if not any(mask):
        mask = [k is not None for k in kinds]  # all plain: still needs typing as numbers
    options = [
        Option("auto", [_step("parse_numbers", column=col, notation="auto")], recommended=True),
        Option("comma", [_step("parse_numbers", column=col, notation="comma")]),
        Option("point", [_step("parse_numbers", column=col, notation="point")]),
    ]
    issue = Issue(
        f"number_locale:{col}",
        "number_locale",
        "consistency",
        col,
        sum(mask),
        {"comma": comma, "point": point},
        options,
    )
    return [
        _finish(
            issue,
            base,
            dc,
            _examples(base, mask, col),
            [col],
            lambda d: kpis.total_spend(d, dc.default_currency, dominant_only=True),
            "total_spend",
            kpi_before=kpis.total_spend(base, dc.default_currency, naive=True, dominant_only=True),
        )
    ]


def detect_currency(base: pd.DataFrame, dc: DetectContext) -> list[Issue]:
    if "currency" not in base.columns or "amount_original" not in base.columns:
        return []
    row_codes = [None if c is None else str(c).strip().upper() for c in _strings(base["currency"])]
    codes = Counter(c for c in row_codes if c)
    if len(codes) < 2:
        return []
    dominant = codes.most_common(1)[0][0]
    mask = [c is not None and c != dominant for c in row_codes]
    options = [
        Option(
            f"to_{t.lower()}",
            [_step("convert_currency", to=t)],
            recommended=t == "CAD",
            params={"currency": t},
        )
        for t in ("CAD", "COP", "USD")
    ]
    options.append(
        Option(
            "keep_add_cad",
            [_step("convert_currency", to="CAD", mode="add_column")],
            params={"currency": "CAD"},
        )
    )
    params = {
        "breakdown": [{"currency": c, "rows": n} for c, n in codes.most_common()],
        "n": len(codes),
        "dominant": dominant,
        # COP rates are derived from TRM × USD/CAD, so their source line names both.
        "fx_source": dc.ctx.fx.sources.get("COP" if "COP" in codes else "USD", ""),
    }
    issue = Issue(
        "mixed_currency:currency",
        "mixed_currency",
        "consistency",
        "currency",
        sum(mask),
        params,
        options,
    )
    return [
        _finish(
            issue,
            base,
            dc,
            _examples(base, mask, "amount_original"),
            ["amount_original", "currency"],
            lambda d: kpis.total_spend(d, dc.default_currency),
            "total_spend",
        )
    ]


def detect_text_variants(base: pd.DataFrame, dc: DetectContext) -> list[Issue]:
    """Entity / supplier names written several ways (case, accents, spaces)."""
    issues = []
    for col in ("entity_name", "supplier_name"):
        if not _text_column(base, col):
            continue
        values = _strings(base[col])
        counts = Counter(v for v in values if v is not None)
        groups: dict[str, list[tuple[int, str]]] = {}
        for v, n in counts.items():
            groups.setdefault(normalize_token(v), []).append((n, v))
        keep = {key: max(members)[1] for key, members in groups.items()}
        mask = [v is not None and v != keep[normalize_token(v)] for v in values]
        affected = sum(mask)
        if affected < max(5, len(base) * 0.001):
            continue
        options = [
            Option("unify", [_step("unify_variants", column=col)], recommended=True),
            Option(
                "upper", [_step("normalize_text", column=col, case="upper", remove_accents=True)]
            ),
            Option("keep", []),
        ]
        n_groups = sum(1 for members in groups.values() if len(members) > 1)
        issue = Issue(
            f"text_variants:{col}",
            "text_variants",
            "consistency",
            col,
            affected,
            {"groups": n_groups, "rows": affected},
            options,
        )
        kpi: Kpi = lambda d, c=col: kpis.distinct_values(d, c)  # noqa: E731
        issues.append(
            _finish(issue, base, dc, _examples(base, mask, col), [col], kpi, f"distinct_{col}")
        )
    return issues


def detect_categories(base: pd.DataFrame, dc: DetectContext) -> list[Issue]:
    """Award types in source language/codes → canonical EN labels."""
    col = "award_type"
    if not _text_column(base, col):
        return []
    values = _strings(base[col])
    mask = [v is not None and AWARD_TYPES.get(normalize_token(v), "other") != v for v in values]
    if not any(mask):
        return []
    distinct = {v for v in values if v is not None}
    options = [
        Option(
            "standardize",
            [_step("standardize_categories", column=col, mapping="award_type")],
            recommended=True,
        ),
        Option("keep", []),
    ]
    issue = Issue(
        f"category_labels:{col}",
        "category_labels",
        "consistency",
        col,
        sum(mask),
        {"distinct": len(distinct), "labels": ", ".join(CANONICAL_AWARD_TYPES)},
        options,
    )
    return [
        _finish(
            issue,
            base,
            dc,
            _examples(base, mask, col),
            [col],
            kpis.direct_award_share,
            "direct_award_share",
        )
    ]


def detect_outliers(base: pd.DataFrame, dc: DetectContext) -> list[Issue]:
    col = "amount_original"
    if col not in base.columns:
        return []
    numbers = _as_numbers(base[col])
    bounds = _outlier_bounds([n for n in numbers if n is not None], 3.0)
    if bounds is None:
        return []
    low, high = bounds
    mask = [n is not None and (n < low or n > high) for n in numbers]
    if not any(mask):
        return []
    options = [
        Option("flag", [_step("handle_outliers", column=col, action="flag")], recommended=True),
        Option("cap", [_step("handle_outliers", column=col, action="cap")]),
        Option("keep", []),
    ]
    currency = kpis.total_spend(base, dc.default_currency).get("currency")
    params = {
        "count": sum(mask),
        "high": round(high, 2),
        "low": round(low, 2),
        "currency": currency,
    }
    issue = Issue(f"outliers:{col}", "outliers", "validity", col, sum(mask), params, options)
    order = sorted(range(len(numbers)), key=lambda i: -(numbers[i] or 0))
    top = [int(base[ROW_ID].iat[i]) for i in order if mask[i]][:EXAMPLES]
    return [
        _finish(
            issue,
            base,
            dc,
            top,
            [col],
            lambda d: kpis.total_spend(d, dc.default_currency),
            "total_spend",
        )
    ]


def detect_type_casting(base: pd.DataFrame, dc: DetectContext) -> list[Issue]:
    col = "n_bidders"
    if not _text_column(base, col):
        return []
    mask = [v is not None for v in _strings(base[col])]
    if not any(mask):
        return []
    options = [
        Option("to_integer", [_step("cast_type", column=col, to="integer")], recommended=True),
        Option("keep", []),
    ]
    issue = Issue(
        f"type_casting:{col}",
        "type_casting",
        "validity",
        col,
        sum(mask),
        {"count": sum(mask)},
        options,
    )
    return [_finish(issue, base, dc, _examples(base, mask, col), [col])]


PIPELINE: tuple[Callable[[pd.DataFrame, DetectContext], list[Issue]], ...] = (
    detect_header_mapping,
    detect_pii,
    detect_duplicates,
    detect_missing,
    detect_time_zone,
    detect_date_format,
    detect_number_locale,
    detect_currency,
    detect_text_variants,
    detect_categories,
    detect_outliers,
    detect_type_casting,
)
ISSUE_TYPES = (
    "header_mapping",
    "pii",
    "duplicates",
    "missing_values",
    "time_zone",
    "date_format",
    "number_locale",
    "mixed_currency",
    "text_variants",
    "category_labels",
    "outliers",
    "type_casting",
)


def detect_issues(
    staged: pd.DataFrame, profile: dict[str, Any], ctx: Context, default_currency: str | None
) -> list[Issue]:
    """Run every detector in pipeline order, applying each recommended option before the
    next detector looks at the data."""
    dc = DetectContext(ctx, profile, default_currency)
    base = staged.copy()
    base[ROW_ID] = range(len(base))
    found: list[Issue] = []
    for detector in PIPELINE:
        for issue in detector(base, dc):
            found.append(issue)
            base = apply_steps(base, issue.recommended.steps, ctx)
    return found


def recommended_steps(issues: list[Issue]) -> list[Step]:
    return [step for issue in issues for step in issue.recommended.steps]
