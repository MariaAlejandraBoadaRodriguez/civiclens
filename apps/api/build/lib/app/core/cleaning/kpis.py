"""KPIs used to show the impact of each cleaning option (Cleaning Studio KPI strip).

Values are machine data (numbers, ISO codes); labels are localized by the API layer.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.core.cleaning.ops import _as_dates, _as_numbers, _strings
from app.core.ingest.locale_parse import NumberLocale, classify_date, classify_number, parse_number

AMOUNT, CURRENCY, DATE = "amount_original", "currency", "signed_date"


def _currencies(df: pd.DataFrame, default: str | None) -> set[str]:
    if CURRENCY not in df.columns:
        return {default} if default else set()
    return {
        str(c).strip().upper() for c in _strings(df[CURRENCY]) if c is not None and str(c).strip()
    }


def total_spend(
    df: pd.DataFrame,
    default_currency: str | None,
    naive: bool = False,
    dominant_only: bool = False,
) -> dict[str, Any]:
    """Sum of contract values. ``None`` when several currencies are mixed (not comparable),
    unless ``dominant_only`` restricts the sum to rows in the most frequent currency.
    ``naive`` reads every amount as plain English notation — what a spreadsheet would do."""
    if AMOUNT not in df.columns:
        return {"value": None, "currency": None, "reason": "no_amount"}
    if "amount_cad" in df.columns:
        values = _as_numbers(df["amount_cad"])
        return {"value": round(sum(v for v in values if v is not None), 2), "currency": "CAD"}
    codes = _currencies(df, default_currency)
    keep = [True] * len(df)
    currency = next(iter(codes), default_currency)
    if len(codes) > 1:
        if not dominant_only:
            return {"value": None, "currency": None, "reason": "mixed_currencies"}
        row_codes = [None if c is None else str(c).strip().upper() for c in _strings(df[CURRENCY])]
        currency = max(codes, key=row_codes.count)
        keep = [c == currency for c in row_codes]
    if naive:
        # What a spreadsheet in English settings reads: values in comma notation are text.
        values = [
            parse_number(v, NumberLocale.POINT)
            if classify_number(str(v)) in (NumberLocale.POINT, NumberLocale.PLAIN)
            else None
            for v in _strings(df[AMOUNT])
        ]
    else:
        values = _as_numbers(df[AMOUNT])
    total = sum(v for v, k in zip(values, keep, strict=True) if v is not None and k)
    result: dict[str, Any] = {"value": round(total, 2), "currency": currency}
    if len(codes) > 1:
        result["scope"] = "dominant_currency"
    return result


def contract_count(df: pd.DataFrame, default_currency: str | None = None) -> dict[str, Any]:
    return {"value": len(df), "currency": None}


def distinct_values(df: pd.DataFrame, column: str) -> dict[str, Any]:
    if column not in df.columns:
        return {"value": None, "currency": None}
    return {"value": int(df[column].dropna().astype(str).str.strip().nunique()), "currency": None}


def readable_dates(df: pd.DataFrame, strict: bool) -> dict[str, Any]:
    """Share of signed dates a single-format reader understands (``strict``: only the
    dominant format) vs. after parsing every format."""
    if DATE not in df.columns:
        return {"value": None, "currency": None}
    values = _strings(df[DATE])
    non_null = [v for v in values if v is not None]
    if not non_null:
        return {"value": None, "currency": None}
    if strict and not isinstance(non_null[0], pd.Timestamp):
        formats = [classify_date(v) for v in non_null]
        dominant = max(set(formats), key=formats.count)
        ok = sum(1 for f in formats if f == dominant)
    else:
        ok = sum(1 for d in _as_dates(df[DATE]) if d is not None)
    return {"value": round(ok / len(non_null), 4), "currency": None, "unit": "ratio"}


def direct_award_share(df: pd.DataFrame) -> dict[str, Any]:
    """Share of contracts awarded directly; only defined once award types are canonical."""
    if "award_type" not in df.columns:
        return {"value": None, "currency": None}
    values = [v for v in _strings(df["award_type"]) if v is not None]
    if not values or not set(values) <= {"direct", "open", "limited", "other"}:
        return {"value": None, "currency": None, "unit": "ratio", "reason": "not_standardized"}
    return {
        "value": round(values.count("direct") / len(values), 4),
        "currency": None,
        "unit": "ratio",
    }
