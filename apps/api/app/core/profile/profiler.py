"""Per-column profile of an all-string DataFrame (raw layer) and the dataset quality score.

Statistics are computed on unique values weighted by their counts, so a 50k-row file
profiles in a few seconds. Type inference uses the most frequent unique values (up to
``SAMPLE_UNIQUES``); invalid / inconsistent value sets use every unique value so the
row-level quality dimensions are exact. Deterministic: no randomness.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import pandas as pd

from app.core.ingest import language
from app.core.ingest.headers_map import BY_NAME, FieldType, HeaderMatch, map_headers
from app.core.ingest.locale_parse import (
    DateFormat,
    NumberLocale,
    classify_date,
    classify_number,
    is_null_token,
    normalize_token,
    parse_bool,
    parse_date,
    parse_number,
)
from app.core.profile import quality_score
from app.core.profile.pii import detect_pii

SAMPLE_UNIQUES = 5000
TOP_N = 5
ISO_CURRENCIES = frozenset({"COP", "CAD", "USD", "EUR", "MXN", "GBP"})
NUMERIC = ("number", "integer")
TEMPORAL = ("date", "datetime")

Pairs = list[tuple[str, int]]


def _share(pairs: Pairs, pred) -> float:
    total = sum(n for _, n in pairs)
    return sum(n for v, n in pairs if pred(v)) / total if total else 0.0


def _sample(pairs: Pairs) -> Pairs:
    """Most frequent uniques plus an evenly strided slice of the long tail, with tail
    weights scaled by the stride so weighted shares stay representative."""
    if len(pairs) <= SAMPLE_UNIQUES:
        return pairs
    head = pairs[:1000]
    tail = pairs[1000:]
    stride = max(1, len(tail) // (SAMPLE_UNIQUES - 1000))
    return head + [(v, n * stride) for v, n in tail[::stride]]


def _infer_type(pairs: Pairs, n_distinct: int, n_rows: int) -> str:
    if not pairs:
        return "string"
    if n_distinct <= 4 and _share(pairs, lambda v: parse_bool(v) is not None) >= 0.95:
        return "boolean"
    date_share = _share(pairs, lambda v: classify_date(v) is not None)
    number_share = _share(pairs, lambda v: parse_number(v) is not None)
    if date_share >= 0.6 and date_share >= number_share * 0.9:
        has_time = any(
            (d := parse_date(v)) is not None and (d.hour or d.minute or d.second)
            for v, _ in pairs[:500]
        )
        return "datetime" if has_time else "date"
    if number_share >= 0.6:
        integral = all(
            (x := parse_number(v)) is None or float(x).is_integer() for v, _ in pairs[:2000]
        )
        return "integer" if integral else "number"
    if n_distinct <= max(30, n_rows * 0.01):
        return "category"
    return "string"


def _invalid_values(kind: str, canonical_type: str | None, pairs: Pairs) -> set[str]:
    """Non-null values that do not parse as the column's type."""
    if canonical_type == FieldType.CURRENCY:
        return {v for v, _ in pairs if v.strip().upper() not in ISO_CURRENCIES}
    if kind in NUMERIC:
        return {v for v, _ in pairs if parse_number(v) is None}
    if kind in TEMPORAL:
        return {v for v, _ in pairs if parse_date(v) is None}
    if kind == "boolean":
        return {v for v, _ in pairs if parse_bool(v) is None}
    return set()


def _inconsistent_values(kind: str, pairs: Pairs) -> tuple[set[str], dict[str, int]]:
    """Values written differently from the column's dominant notation / spelling,
    plus the notation histogram shown in the UI."""
    if kind in NUMERIC:
        notes: Counter[str] = Counter()
        by_value: dict[str, str] = {}
        for v, n in pairs:
            loc = classify_number(v)
            if loc in (NumberLocale.POINT, NumberLocale.COMMA):
                notes[loc.value] += n
                by_value[v] = loc.value
        if len(notes) < 2:
            return set(), dict(notes)
        dominant = notes.most_common(1)[0][0]
        return {v for v, loc in by_value.items() if loc != dominant}, dict(notes)
    if kind in TEMPORAL:
        fmts: Counter[str] = Counter()
        by_value = {}
        for v, n in pairs:
            fmt = classify_date(v)
            if fmt is not None:
                # Ambiguous slashed dates join whichever slashed family they are read as.
                family = (
                    "slashed"
                    if fmt in (DateFormat.DMY, DateFormat.MDY, DateFormat.AMBIGUOUS)
                    else fmt
                )
                fmts[fmt.value] += n
                by_value[v] = f"{family}:{fmt.value}"
        families: Counter[str] = Counter()
        for key, n in ((by_value[v], n) for v, n in pairs if v in by_value):
            families[key.split(":")[0]] += n
        if not families:
            return set(), dict(fmts)
        dominant_family = families.most_common(1)[0][0]
        bad = {v for v, key in by_value.items() if key.split(":")[0] != dominant_family}
        if dominant_family == "slashed" and fmts.get("dmy") and fmts.get("mdy"):
            minority = "mdy" if fmts["dmy"] >= fmts["mdy"] else "dmy"
            bad |= {v for v, key in by_value.items() if key.endswith(":" + minority)}
        return bad, dict(fmts)
    if kind in ("category", "string", "boolean"):
        groups: dict[str, list[tuple[str, int]]] = defaultdict(list)
        for v, n in pairs:
            groups[normalize_token(v)].append((v, n))
        bad: set[str] = set()
        for members in groups.values():
            if len(members) > 1:
                keep = max(members, key=lambda m: (m[1], m[0]))[0]
                bad |= {v for v, _ in members if v != keep}
        return bad, {}
    return set(), {}


def profile_column(
    header: str, series: pd.Series, match: HeaderMatch | None, n_rows: int
) -> tuple[dict[str, Any], set[str], set[str], set[str]]:
    """Profile one column. Also returns the sets of null-coded, invalid and inconsistent
    values (used for row-level quality and, in slice 5b, by the issue detectors)."""
    counts = series.value_counts(dropna=False)
    nulls: Counter[str] = Counter()
    pairs: Pairs = []
    for value, n in counts.items():
        if value is None or (isinstance(value, float) and value != value):
            nulls[""] += int(n)
        elif is_null_token(value):
            nulls[str(value)] += int(n)
        else:
            pairs.append((str(value), int(n)))
    pairs.sort(key=lambda p: (-p[1], p[0]))
    null_count = sum(nulls.values())
    non_null = n_rows - null_count
    sample = _sample(pairs)

    canonical = match.canonical_field if match else None
    canonical_type = BY_NAME[canonical].type.value if canonical else None
    inferred = _infer_type(sample, len(pairs), n_rows)
    if canonical_type == FieldType.CURRENCY:
        inferred = "category"
    # Validity follows the canonical type when the column is mapped (ids stay strings).
    if canonical_type in (FieldType.DATE, FieldType.NUMBER, FieldType.INTEGER, FieldType.CURRENCY):
        validity_kind = "date" if canonical_type == FieldType.DATE else inferred
        if canonical_type in (FieldType.NUMBER, FieldType.INTEGER):
            validity_kind = "number"
    elif canonical_type:
        validity_kind = "string"
    else:
        validity_kind = inferred
    invalid = _invalid_values(validity_kind, canonical_type, pairs)
    inconsistent, notations = _inconsistent_values(inferred, pairs)
    invalid_n = sum(n for v, n in pairs if v in invalid)
    inconsistent_n = sum(n for v, n in pairs if v in inconsistent)

    parsed: list = []
    if inferred in NUMERIC:
        parsed = [x for v, _ in pairs[:SAMPLE_UNIQUES] if (x := parse_number(v)) is not None]
    elif inferred in TEMPORAL:
        parsed = [
            d.replace(tzinfo=None)
            for v, _ in pairs[:SAMPLE_UNIQUES]
            if (d := parse_date(v)) is not None
        ]

    text_values = [v for v, _ in sample[:400]] if inferred in ("string", "category") else []
    pii = detect_pii(header, [v for v, _ in sample])
    profile = {
        "source_header": header,
        "canonical_field": canonical,
        "canonical_type": canonical_type,
        "mapping_confidence": match.confidence if match else 0.0,
        "needs_check": bool(match and match.needs_check),
        "candidates": list(match.candidates) if match else [],
        "inferred_type": inferred,
        "validity": round(1 - invalid_n / non_null, 4) if non_null else 1.0,
        "consistency": round(1 - inconsistent_n / non_null, 4) if non_null else 1.0,
        "notations": notations,
        "null_ratio": round(null_count / n_rows, 4) if n_rows else 0.0,
        "null_tokens": dict(nulls.most_common(6)),
        "non_null": non_null,
        "distinct": len(pairs),
        "min": str(min(parsed)) if parsed else None,
        "max": str(max(parsed)) if parsed else None,
        "top_values": [{"value": v, "count": n} for v, n in pairs[:TOP_N]],
        "data_lang": language.detect_values(text_values),
        "text_weight": len(text_values),
        "pii_kind": pii.value if pii else None,
    }
    null_values = {k for k in nulls if k}
    return profile, null_values, invalid, inconsistent


def profile_frame(df: pd.DataFrame) -> dict[str, Any]:
    """Full profile: columns, data language, duplicates and the quality score.

    Quality dimensions are row-level on the canonical (mapped) columns — the ones KPIs
    are computed from — so one messy date column visibly lowers the score.
    """
    headers = [str(c) for c in df.columns]
    matches = {m.source_header: m for m in map_headers(headers)}
    n_rows = len(df)
    columns: list[dict[str, Any]] = []
    row_null = pd.Series(0, index=df.index)
    row_invalid = pd.Series(False, index=df.index)
    row_inconsistent = pd.Series(False, index=df.index)
    mapped_cells = 0
    for h in headers:
        profile, null_values, invalid, inconsistent = profile_column(
            h, df[h], matches.get(h), n_rows
        )
        columns.append(profile)
        if not profile["canonical_field"]:
            continue
        col = df[h]
        is_null = col.isna() | col.isin(null_values)
        row_null += is_null.astype(int)
        mapped_cells += n_rows
        if invalid:
            row_invalid |= col.isin(invalid)
        if inconsistent:
            row_inconsistent |= col.isin(inconsistent)

    dup_ratio = float(df.astype(str).duplicated().mean()) if n_rows else 0.0
    key_cols = [
        c["source_header"]
        for name in ("contract_id", "entity_id")
        for c in columns
        if c["canonical_field"] == name
    ]
    has_key = any(c["canonical_field"] == "contract_id" for c in columns)
    key_dup = float(df[key_cols].astype(str).duplicated().mean()) if has_key and n_rows else 0.0

    if mapped_cells:
        completeness = 1 - row_null.sum() / mapped_cells
    else:
        completeness = 1 - sum(c["null_ratio"] for c in columns) / max(1, len(columns))
    score = quality_score.compute(
        completeness=completeness,
        uniqueness=1 - max(dup_ratio, key_dup),
        validity=1 - float(row_invalid.mean()) if n_rows else 1.0,
        consistency=1 - float(row_inconsistent.mean()) if n_rows else 1.0,
    )
    shares = language.combine((c["data_lang"], c["text_weight"]) for c in columns if c["data_lang"])
    return {
        "rows": n_rows,
        "columns": len(headers),
        "duplicate_rows": int(round(dup_ratio * n_rows)),
        "duplicate_keys": int(round(key_dup * n_rows)),
        "invalid_rows": int(row_invalid.sum()),
        "inconsistent_rows": int(row_inconsistent.sum()),
        "data_lang": shares,
        "data_lang_label": language.dominant(shares),
        "quality": score.to_dict(),
        "columns_profile": columns,
    }
