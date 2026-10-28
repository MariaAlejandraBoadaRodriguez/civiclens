"""Cleaning operations: pure functions ``(df, ctx, **args) -> new DataFrame``.

Rules every operation follows (ADR-0006):
- never mutates its input; same input + args → same output (no randomness, no clock);
- only depends on pandas, the standard library and ``locale_parse`` — so the exported
  pandas script can embed this file verbatim and reproduce the result exactly;
- column names are canonical (English) when the column was mapped, original otherwise.

``ctx`` carries read-only context that is not part of the recipe JSON, e.g. the FX table.
"""

from __future__ import annotations

import bisect
import csv
import hashlib
import math
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.ingest.locale_parse import (
    NumberLocale,
    infer_dayfirst,
    infer_number_locale,
    is_null_token,
    normalize_token,
    parse_date,
    parse_number,
    strip_accents,
)

# --------------------------------------------------------------------------- context


@dataclass(frozen=True)
class FxTable:
    """Monthly CAD value of one unit of each currency (data/fx_rates.csv)."""

    rates: dict[str, dict[str, float]] = field(default_factory=dict)  # currency → month → CAD
    sources: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_csv(cls, path: str | Path) -> FxTable:
        rates: dict[str, dict[str, float]] = defaultdict(dict)
        sources: dict[str, str] = {}
        with open(path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                rates[row["currency"]][row["month"]] = float(row["cad_per_unit"])
                sources[row["currency"]] = row["source"]
        return cls(dict(rates), sources)

    def cad_per_unit(self, currency: str, month: str) -> float | None:
        series = self.rates.get(currency)
        if not series:
            return None
        if month in series:
            return series[month]
        months = sorted(series)
        i = bisect.bisect_left(months, month)  # outside the table → nearest month
        return series[months[min(max(i - 1, 0), len(months) - 1)] if i else months[0]]

    def convert(self, amount: float, src: str, dst: str, month: str) -> float | None:
        a, b = self.cad_per_unit(src, month), self.cad_per_unit(dst, month)
        if a is None or b is None:
            return None
        return amount * a / b


@dataclass(frozen=True)
class Context:
    fx: FxTable = field(default_factory=FxTable)


# --------------------------------------------------------------------------- helpers


def _missing(value: object) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value)) or value is pd.NaT


def is_text(series: pd.Series) -> bool:
    """Object or string dtype (pandas 3 infers ``str`` for lists of strings)."""
    return pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)


def _strings(series: pd.Series) -> list[object]:
    return [None if _missing(v) else v for v in series.tolist()]


def _as_numbers(series: pd.Series, notation: str = "auto") -> list[float | None]:
    values = _strings(series)
    if all(v is None or isinstance(v, int | float) for v in values):
        return [None if v is None else float(v) for v in values]
    if notation == "auto":
        locale = infer_number_locale(values) or NumberLocale.POINT
    else:
        locale = NumberLocale.COMMA if notation == "comma" else NumberLocale.POINT
    # Unambiguous values always follow their own notation; ``notation`` only decides how
    # ambiguous ones (``1.234`` / ``1,234``) are read.
    return [parse_number(v, locale) for v in values]


def _as_dates(series: pd.Series, dayfirst: bool | None = None) -> list[datetime | None]:
    values = _strings(series)
    if dayfirst is None:
        dayfirst = infer_dayfirst(values)
    out = []
    for v in values:
        if v is None:
            out.append(None)
        elif isinstance(v, datetime):
            out.append(v)
        elif isinstance(v, pd.Timestamp):
            out.append(v.to_pydatetime())
        else:
            out.append(parse_date(v, dayfirst=dayfirst))
    return out


def _month(value: object) -> str | None:
    if isinstance(value, pd.Timestamp | datetime):
        return f"{value.year:04d}-{value.month:02d}"
    d = parse_date(value)
    return f"{d.year:04d}-{d.month:02d}" if d else None


def _set_text(df: pd.DataFrame, column: str, values: list[object]) -> None:
    """Assign a text column keeping real ``None`` for nulls (object dtype), so behaviour does
    not depend on the pandas version's default string dtype."""
    df[column] = pd.Series(values, index=df.index, dtype=object)


def _float_column(values: list[float | None]) -> pd.Series:
    return pd.Series([math.nan if v is None else v for v in values], dtype="float64")


def _key_frame(df: pd.DataFrame, columns: list[str]) -> list[tuple]:
    """Row keys ignoring case, accents and spacing (each unique value normalized once)."""
    keyed = []
    for c in columns:
        values = df[c].astype(str).tolist()
        cache = {v: normalize_token(v) for v in set(values)}
        keyed.append([cache[v] for v in values])
    return list(zip(*keyed, strict=True))


# --------------------------------------------------------------------------- operations


def rename_columns(df: pd.DataFrame, ctx: Context, mapping: dict[str, str]) -> pd.DataFrame:
    """Header-mapping overrides chosen by the user."""
    return df.rename(columns={k: v for k, v in mapping.items() if k in df.columns})


def drop_columns(df: pd.DataFrame, ctx: Context, columns: list[str]) -> pd.DataFrame:
    return df.drop(columns=[c for c in columns if c in df.columns])


def mask_columns(
    df: pd.DataFrame, ctx: Context, columns: list[str], salt: str = "civiclens"
) -> pd.DataFrame:
    """Replace personal data with a stable, irreversible pseudonym (same value → same mask)."""
    out = df.copy()
    for col in columns:
        if col in out.columns:
            _set_text(
                out,
                col,
                [
                    None
                    if _missing(v) or str(v) == ""
                    else "MASK-" + hashlib.sha256(f"{salt}:{v}".encode()).hexdigest()[:10]
                    for v in out[col].tolist()
                ],
            )
    return out


def standardize_nulls(
    df: pd.DataFrame, ctx: Context, columns: list[str] | None = None
) -> pd.DataFrame:
    """Turn coded missing values (``N/A``, ``-``, ``sin dato``, ``non disponible``…) into nulls."""
    out = df.copy()
    for col in columns or list(out.columns):
        if col in out.columns and is_text(out[col]):
            _set_text(out, col, [None if is_null_token(v) else v for v in out[col].tolist()])
    return out


def drop_duplicates(
    df: pd.DataFrame, ctx: Context, mode: str = "exact", keep: str = "first"
) -> pd.DataFrame:
    """``mode``: ``exact`` (identical rows) or ``near`` (identical ignoring case, accents and
    spaces). ``keep``: ``first``, ``last`` or ``flag`` (keep all, add ``is_duplicate``)."""
    columns = [c for c in df.columns if not str(c).startswith("__")]  # "__row": preview bookkeeping
    if mode == "near":
        keys = _key_frame(df, columns)
        dup = pd.Series(keys).duplicated(keep="first" if keep == "flag" else keep).to_numpy()
    else:
        dup = (
            df[columns].astype(str).duplicated(keep="first" if keep == "flag" else keep).to_numpy()
        )
    if keep == "flag":
        out = df.copy()
        out["is_duplicate"] = dup
        return out
    return df.loc[~dup].reset_index(drop=True)


def parse_numbers(
    df: pd.DataFrame, ctx: Context, column: str, notation: str = "auto"
) -> pd.DataFrame:
    """Parse a text column into numbers. Each value is read in its own notation; ambiguous
    ones (``1.234``) follow ``notation`` — ``auto`` = the column's dominant notation."""
    out = df.copy()
    out[column] = _float_column(_as_numbers(out[column], notation))
    return out


def parse_dates(
    df: pd.DataFrame, ctx: Context, column: str, dayfirst: bool = True, timezone: str = "utc"
) -> pd.DataFrame:
    """Parse mixed date formats. Ambiguous ``05/06/2024`` follows ``dayfirst``.
    ``timezone``: ``utc`` converts offsets to UTC; ``drop`` keeps the local wall time."""
    out = df.copy()
    values = []
    for d in _as_dates(out[column], dayfirst):
        if d is not None and d.tzinfo is not None:
            if timezone == "utc":
                d = (d - d.utcoffset()).replace(tzinfo=None)
            else:
                d = d.replace(tzinfo=None)
        values.append(d)
    out[column] = pd.to_datetime(pd.Series(values, dtype=object), errors="coerce")
    return out


def normalize_timezones(
    df: pd.DataFrame, ctx: Context, column: str, to: str = "utc"
) -> pd.DataFrame:
    """Remove time-zone offsets from date strings. ``utc`` converts to UTC first
    (``2026-05-01T00:00:00-04:00`` → ``2026-05-01T04:00:00``); ``local`` keeps the wall time."""
    out = df.copy()
    result = []
    for v in _strings(out[column]):
        d = parse_date(v) if isinstance(v, str) else None
        if d is None or d.tzinfo is None:
            result.append(v)
            continue
        if to == "utc":
            d = d - d.utcoffset()
        result.append(d.replace(tzinfo=None).isoformat(timespec="seconds"))
    _set_text(out, column, result)
    return out


def convert_currency(
    df: pd.DataFrame,
    ctx: Context,
    to: str = "CAD",
    amount: str = "amount_original",
    currency: str = "currency",
    date: str = "signed_date",
    mode: str = "replace",
    default_currency: str | None = None,
) -> pd.DataFrame:
    """Convert amounts to one currency with the rate of each row's month (FX table).
    ``mode``: ``replace`` overwrites amount + currency; ``add_column`` keeps originals and
    adds ``amount_<to>``."""
    out = df.copy()
    amounts = _as_numbers(out[amount])
    if currency in out.columns:
        codes = [None if _missing(c) else str(c).strip().upper() for c in out[currency].tolist()]
    else:
        codes = [default_currency] * len(out)
    months = [
        _month(v) for v in (_strings(out[date]) if date in out.columns else [None] * len(out))
    ]
    converted: list[float | None] = []
    for a, c, m in zip(amounts, codes, months, strict=True):
        if a is None or c is None:
            converted.append(None)
        elif c == to:
            converted.append(a)
        else:
            value = ctx.fx.convert(a, c, to, m or "")
            converted.append(None if value is None else round(value, 2))
    if mode == "add_column":
        out[f"amount_{to.lower()}"] = _float_column(converted)
    else:
        out[amount] = _float_column(converted)
        _set_text(
            out,
            currency,
            [to if a is not None else c for a, c in zip(converted, codes, strict=True)],
        )
    return out


def normalize_text(
    df: pd.DataFrame,
    ctx: Context,
    column: str,
    case: str = "keep",
    remove_accents: bool = False,
    trim: bool = True,
) -> pd.DataFrame:
    """Trim / collapse spaces, change case and optionally remove accents."""
    out = df.copy()

    def fix(v: object) -> object:
        if _missing(v):
            return None
        text = " ".join(str(v).split()) if trim else str(v)
        if remove_accents:
            text = strip_accents(text)
        return {"upper": text.upper(), "lower": text.lower(), "title": text.title()}.get(case, text)

    _set_text(out, column, [fix(v) for v in out[column].tolist()])
    return out


def unify_variants(df: pd.DataFrame, ctx: Context, column: str) -> pd.DataFrame:
    """Replace spelling variants (case, accents, spaces) with the most frequent spelling."""
    out = df.copy()
    values = _strings(out[column])
    counts = Counter(v for v in values if v is not None)
    groups: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for v, n in counts.items():
        groups[normalize_token(v)].append((n, str(v)))
    canonical = {key: max(members)[1].strip() for key, members in groups.items()}
    _set_text(out, column, [None if v is None else canonical[normalize_token(v)] for v in values])
    return out


def handle_missing(
    df: pd.DataFrame, ctx: Context, column: str, action: str = "keep", value: Any = None
) -> pd.DataFrame:
    """``drop_rows`` removes rows without a value, ``fill`` writes ``value``, ``flag`` adds
    ``<column>_missing``, ``keep`` does nothing (documented decision)."""
    out = df.copy()
    missing = [_missing(v) or is_null_token(v) for v in out[column].tolist()]
    if action == "drop_rows":
        return out.loc[[not m for m in missing]].reset_index(drop=True)
    if action == "fill":
        _set_text(
            out,
            column,
            [value if m else v for v, m in zip(out[column].tolist(), missing, strict=True)],
        )
    elif action == "flag":
        out[f"{column}_missing"] = missing
    return out


def _outlier_bounds(values: list[float], k: float) -> tuple[float, float] | None:
    logs = sorted(math.log10(v) for v in values if v and v > 0)
    if len(logs) < 8:
        return None
    q1, q3 = logs[len(logs) // 4], logs[(3 * len(logs)) // 4]
    iqr = q3 - q1
    return 10 ** (q1 - k * iqr), 10 ** (q3 + k * iqr)


def handle_outliers(
    df: pd.DataFrame, ctx: Context, column: str, action: str = "flag", k: float = 3.0
) -> pd.DataFrame:
    """IQR on log10 amounts (spend is heavy-tailed). ``flag`` adds ``<column>_outlier``,
    ``cap`` clips to the fence, ``keep`` changes nothing."""
    out = df.copy()
    numbers = _as_numbers(out[column])
    bounds = _outlier_bounds([n for n in numbers if n is not None], k)
    if bounds is None or action == "keep":
        return out
    low, high = bounds
    if action == "cap":
        out[column] = _float_column(
            [None if n is None else round(min(max(n, low), high), 2) for n in numbers]
        )
    else:
        out[f"{column}_outlier"] = [n is not None and (n < low or n > high) for n in numbers]
    return out


def cast_type(df: pd.DataFrame, ctx: Context, column: str, to: str = "integer") -> pd.DataFrame:
    out = df.copy()
    if to == "string":
        _set_text(out, column, [None if _missing(v) else str(v) for v in out[column].tolist()])
        return out
    numbers = _as_numbers(out[column])
    if to == "integer":
        out[column] = pd.array(
            [None if n is None else int(round(n)) for n in numbers], dtype="Int64"
        )
    else:
        out[column] = _float_column(numbers)
    return out


# Award types → canonical EN labels (direct / open / limited / other). Keys are normalized.
AWARD_TYPES = {
    # Colombia (SECOP II modalidades)
    "contratacion directa": "direct",
    "contratacion directa (con ofertas)": "direct",
    "contratacion regimen especial": "other",
    "contratacion regimen especial (con ofertas)": "other",
    "licitacion publica": "open",
    "licitacion publica acuerdo marco de precios": "open",
    "licitacion obra publica": "open",
    "concurso de meritos abierto": "open",
    "concurso de meritos con lista corta": "limited",
    "seleccion abreviada de menor cuantia": "limited",
    "seleccion abreviada subasta inversa": "limited",
    "seleccion abreviada servicios de salud": "limited",
    "minima cuantia": "limited",
    "enajenacion de bienes con subasta": "other",
    "enajenacion de bienes con sobre cerrado": "other",
    # Canada (solicitation_procedure codes)
    "tc": "open",  # traditional competitive
    "ob": "open",  # open bidding
    "st": "limited",  # selective tendering
    "tn": "direct",  # traditional non-competitive
    "ac": "direct",  # advance contract award notice
    # Québec (OCDS procurementMethod)
    "open": "open",
    "limited": "limited",
    "selective": "limited",
    "direct": "direct",
}
CANONICAL_AWARD_TYPES = ("direct", "open", "limited", "other")
CATEGORY_MAPS = {"award_type": AWARD_TYPES}


def standardize_categories(
    df: pd.DataFrame, ctx: Context, column: str, mapping: str | dict[str, str] = "award_type"
) -> pd.DataFrame:
    """Map source-language category values to EN canonical labels; the original value is
    kept in ``<column>_source`` (ADR-0006 ``label_source``). Unknown values → ``other``."""
    table = (
        CATEGORY_MAPS[mapping]
        if isinstance(mapping, str)
        else {normalize_token(k): v for k, v in mapping.items()}
    )
    out = df.copy()
    values = _strings(out[column])
    _set_text(out, f"{column}_source", values)
    _set_text(
        out, column, [None if v is None else table.get(normalize_token(v), "other") for v in values]
    )
    return out


OPERATIONS: dict[str, Callable[..., pd.DataFrame]] = {
    "rename_columns": rename_columns,
    "drop_columns": drop_columns,
    "mask_columns": mask_columns,
    "standardize_nulls": standardize_nulls,
    "drop_duplicates": drop_duplicates,
    "parse_numbers": parse_numbers,
    "normalize_timezones": normalize_timezones,
    "parse_dates": parse_dates,
    "convert_currency": convert_currency,
    "normalize_text": normalize_text,
    "unify_variants": unify_variants,
    "handle_missing": handle_missing,
    "handle_outliers": handle_outliers,
    "cast_type": cast_type,
    "standardize_categories": standardize_categories,
}


def apply_steps(df: pd.DataFrame, steps: list[dict[str, Any]], ctx: Context) -> pd.DataFrame:
    """Fold the recipe steps over ``df`` (each step: ``{"op": name, "args": {...}}``)."""
    for step in steps:
        df = OPERATIONS[step["op"]](df, ctx, **step.get("args", {}))
    return df


def output_hash(df: pd.DataFrame) -> str:
    """Content hash used to prove replay determinism (CSV is engine-version independent)."""
    text = df.to_csv(index=False, lineterminator="\n", date_format="%Y-%m-%dT%H:%M:%S", na_rep="")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
