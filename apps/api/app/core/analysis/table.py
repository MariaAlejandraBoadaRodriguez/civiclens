"""The generic analysis table: any tabular file → one typed table ``data`` with safe names.

Every dataset gets it, whatever its domain. Each source column becomes one column of ``data``:
a safe snake_case name (``emp.var.rate`` → ``emp_var_rate``), a SQL type parsed with the
column's own number locale and date order, and a *kind* that drives the generated questions,
KPIs, models and charts:

- ``number`` / ``integer`` — quantities; ``binary`` flags a 0/1 column;
- ``boolean`` — yes/no, true/false, sí/no …;
- ``date`` / ``datetime``;
- ``category`` — few distinct labels (region, product, party …);
- ``text`` — free text; ``identifier`` — one distinct value per row (ids, codes, names).

Pure functions on pandas frames; the service layer writes the result to DuckDB.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from app.core.ingest.locale_parse import (
    infer_dayfirst,
    infer_number_locale,
    is_null_token,
    parse_bool,
    parse_date,
    parse_number,
)

NUMERIC_KINDS = ("number", "integer")
TEMPORAL_KINDS = ("date", "datetime")
MAX_CATEGORIES = 200  # more distinct labels than this is text or an identifier
ID_HINT = re.compile(r"(^|_)(id|ids|key|code|codigo|cod|cik|uuid|sku|ref|nit|symbol|no)($|_)")
INTERNAL = ("__",)  # helper columns added by cleaning operations (e.g. __row)


@dataclass
class ColumnMeta:
    name: str  # safe SQL name in table ``data``
    source: str  # the header as written in the file
    kind: str
    sql_type: str
    binary: bool = False
    rows: int = 0
    nulls: int = 0
    distinct: int = 0
    examples: list[str] = field(default_factory=list)
    top: list[dict[str, Any]] = field(default_factory=list)  # most frequent values (categories)
    min: Any = None
    max: Any = None
    mean: float | None = None

    @property
    def null_share(self) -> float:
        return self.nulls / self.rows if self.rows else 0.0

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["null_share"] = round(self.null_share, 4)
        return out


def safe_name(header: str, taken: set[str]) -> str:
    """``"Unit Price (€)"`` → ``unit_price``: unique in ``taken``, never empty or numeric-first."""
    text = unicodedata.normalize("NFKD", str(header)).encode("ascii", "ignore").decode()
    text = re.sub(r"[^0-9a-zA-Z]+", "_", text).strip("_").lower() or "column"
    if text[0].isdigit():
        text = f"c_{text}"
    text = text[:60]
    name, n = text, 2
    while name in taken:
        name, n = f"{text}_{n}", n + 1
    taken.add(name)
    return name


def _strings(series: pd.Series) -> pd.Series:
    """Values as stripped strings with every null token (``n/a``, ``sin dato`` …) as None."""
    values = series.astype(object)
    uniques = pd.unique(values[values.notna()])
    cleaned = {}
    for v in uniques:
        text = str(v).strip()
        cleaned[v] = None if is_null_token(text) else text
    return values.map(
        lambda v: None if v is None or (isinstance(v, float) and v != v) else cleaned.get(v)
    )


def _share(n: int, d: int) -> float:
    return n / d if d else 0.0


def _parse_numbers(text: pd.Series) -> tuple[pd.Series, float]:
    uniques = [u for u in pd.unique(text[text.notna()])]
    locale = infer_number_locale(uniques[:5000])
    parsed = {u: parse_number(u, locale) for u in uniques}
    out = text.map(lambda v: parsed.get(v) if v is not None else None)
    ok = sum(1 for u in uniques if parsed[u] is not None)
    return pd.to_numeric(out, errors="coerce"), _share(ok, len(uniques))


def _parse_dates(text: pd.Series) -> tuple[pd.Series, float]:
    uniques = [u for u in pd.unique(text[text.notna()])]
    dayfirst = infer_dayfirst(uniques[:5000])
    parsed = {}
    for u in uniques:
        d = parse_date(u, dayfirst=dayfirst)
        parsed[u] = d.replace(tzinfo=None) if d is not None else None
    out = text.map(lambda v: parsed.get(v) if v is not None else None)
    ok = sum(1 for u in uniques if parsed[u] is not None)
    return pd.to_datetime(out, errors="coerce"), _share(ok, len(uniques))


def _kind_from_values(text: pd.Series, hint: str | None) -> str:
    """The kind of an all-text column: the profiler's inferred type when given, else a quick
    inference on the distinct values."""
    non_null = text.dropna()
    if non_null.empty:
        return "text"
    if hint in ("number", "integer", "date", "datetime", "boolean"):
        return hint
    uniques = list(pd.unique(non_null))[:3000]
    if len(uniques) <= 4 and all(parse_bool(u) is not None for u in uniques):
        return "boolean"
    numeric = _share(sum(parse_number(u) is not None for u in uniques), len(uniques))
    dates = _share(sum(parse_date(u) is not None for u in uniques[:500]), min(len(uniques), 500))
    if numeric >= 0.9:
        return "number"
    if dates >= 0.9:
        return "date"
    return hint if hint in ("category", "string") else "category"


def _text_kind(name: str, text: pd.Series, distinct: int, non_null: int) -> str:
    """identifier (one value per row: ids, codes, names), category (labels that repeat) or
    text (long free text)."""
    if distinct <= 1:
        return "category"
    avg_len = float(text.dropna().map(len).mean()) if non_null else 0.0
    ratio = _share(distinct, non_null)
    if ratio >= 0.8:
        return "text" if avg_len > 40 else "identifier"
    if ratio <= 0.5 or distinct <= MAX_CATEGORIES:
        return "category"
    return "text" if avg_len > 40 else "identifier"


def build_table(
    frame: pd.DataFrame, hints: dict[str, str] | None = None, sources: dict[str, str] | None = None
) -> tuple[pd.DataFrame, list[ColumnMeta]]:
    """Type every column of ``frame`` (the cleaned or recommended-cleaned layer).

    ``hints`` maps a frame column to the profiler's inferred type; ``sources`` maps it to the
    header as written in the file. Columns already typed by a cleaning step (numbers, dates)
    keep their type. Returns the typed frame (safe column names) and one ``ColumnMeta`` per
    column, in file order."""
    hints, sources = hints or {}, sources or {}
    taken: set[str] = set()
    out: dict[str, pd.Series] = {}
    metas: list[ColumnMeta] = []
    n_rows = len(frame)
    for col in frame.columns:
        if str(col).startswith(INTERNAL):
            continue
        series = frame[col]
        name = safe_name(sources.get(col, col), taken)
        if pd.api.types.is_bool_dtype(series):
            typed, kind = series.astype("boolean"), "boolean"
        elif pd.api.types.is_numeric_dtype(series):
            typed = pd.to_numeric(series, errors="coerce")
            whole = typed.dropna()
            kind = "integer" if len(whole) and (whole % 1 == 0).all() else "number"
        elif pd.api.types.is_datetime64_any_dtype(series):
            typed, kind = pd.to_datetime(series, errors="coerce"), "date"
        else:
            text = _strings(series)
            kind = _kind_from_values(text, hints.get(col))
            typed = text
            if kind in NUMERIC_KINDS:
                typed, ok = _parse_numbers(text)
                whole = typed.dropna()
                kind = "integer" if len(whole) and (whole % 1 == 0).all() else "number"
                if ok < 0.6:  # mostly not numbers after all (codes like "A12"): keep the text
                    typed, kind = text, "category"
            elif kind in TEMPORAL_KINDS:
                typed, ok = _parse_dates(text)
                if ok < 0.6:
                    typed, kind = text, "category"
                elif typed.dropna().dt.normalize().ne(typed.dropna()).any():
                    kind = "datetime"
            elif kind == "boolean":
                typed = text.map(lambda v: parse_bool(v) if v is not None else None).astype(
                    "boolean"
                )
        meta = _describe(name, sources.get(col, str(col)), typed, kind, n_rows)
        out[name] = typed
        metas.append(meta)
    return pd.DataFrame(out, index=frame.index).reset_index(drop=True), metas


def _describe(name: str, source: str, typed: pd.Series, kind: str, n_rows: int) -> ColumnMeta:
    non_null = typed.dropna()
    distinct = int(non_null.nunique())
    sql_type = {
        "number": "DOUBLE",
        "integer": "BIGINT",
        "boolean": "BOOLEAN",
        "date": "DATE",
        "datetime": "TIMESTAMP",
    }.get(kind, "VARCHAR")
    if kind not in NUMERIC_KINDS + TEMPORAL_KINDS + ("boolean",):
        kind = _text_kind(
            name, typed.astype(object).where(typed.notna(), None), distinct, len(non_null)
        )
    elif kind in NUMERIC_KINDS and ID_HINT.search(name):
        # Numeric codes (CIK, station id, sector code): labels, not quantities.
        kind = "identifier" if _share(distinct, len(non_null)) >= 0.8 else "category"
    shown = non_null
    if kind == "integer" or (kind in ("identifier", "category") and sql_type == "BIGINT"):
        # Whole numbers read as floats (NaN forces float64): show 24, not 24.0, so the values
        # match what DuckDB prints for the BIGINT column (target positives compare as text).
        shown = non_null.astype("int64")
    counts = shown.astype(str).value_counts().head(5) if len(non_null) else pd.Series(dtype=int)
    meta = ColumnMeta(
        name=name,
        source=source,
        kind=kind,
        sql_type=sql_type,
        binary=kind == "boolean" or (kind in NUMERIC_KINDS and distinct == 2),
        rows=n_rows,
        nulls=int(n_rows - len(non_null)),
        distinct=distinct,
        examples=[str(v)[:60] for v in counts.index[:3]],
        top=[{"value": str(v)[:80], "count": int(n)} for v, n in counts.items()]
        if kind in ("category", "boolean") or (kind in NUMERIC_KINDS and distinct <= 12)
        else [],
    )
    if kind in NUMERIC_KINDS and len(non_null):
        arr = non_null.to_numpy(dtype=float)
        meta.min, meta.max, meta.mean = float(np.min(arr)), float(np.max(arr)), float(np.mean(arr))
    elif kind in TEMPORAL_KINDS and len(non_null):
        meta.min, meta.max = str(non_null.min().date()), str(non_null.max().date())
    return meta


def for_duckdb(typed: pd.DataFrame, metas: list[ColumnMeta]) -> pd.DataFrame:
    """Column dtypes DuckDB maps to the declared SQL types (dates as dates, not timestamps)."""
    out = typed.copy()
    for m in metas:
        if m.kind == "date":
            out[m.name] = pd.to_datetime(out[m.name], errors="coerce").dt.date
        elif m.kind == "integer":
            out[m.name] = pd.to_numeric(out[m.name], errors="coerce").round().astype("Int64")
        elif m.sql_type == "VARCHAR":
            out[m.name] = (
                out[m.name]
                .astype(object)
                .where(out[m.name].notna(), None)
                .map(lambda v: v if v is None else str(v))
            )
    return out
