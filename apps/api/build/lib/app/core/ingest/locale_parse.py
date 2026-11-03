"""Locale-aware parsing of numbers, dates and null tokens (EN / FR / ES sources).

Pure functions, no I/O. Used by the profiler (type inference, validity) and by the
cleaning operations (slice 5b). Values that cannot be parsed return ``None`` — callers
decide whether that is a null or an invalid value.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta, timezone
from enum import StrEnum

# Tokens that mean "no value" in the three source languages (compared after normalize_token).
NULL_TOKENS = frozenset(
    {
        "",
        "-",
        "--",
        "---",
        ".",
        "?",
        "n/a",
        "na",
        "n.a.",
        "n.d.",
        "nd",
        "nan",
        "null",
        "none",
        "nil",
        "missing",
        "unknown",
        "not available",
        "sin dato",
        "sin datos",
        "sin informacion",
        "no aplica",
        "no definido",
        "no disponible",
        "ninguno",
        "non disponible",
        "non applicable",
        "non defini",
        "inconnu",
        "s.o.",
        "so",
        "aucun",
    }
)

_SPACES = re.compile(r"[\s  ]+")


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def normalize_token(value: object) -> str:
    """Lower-case, accent-free, single-spaced representation used for comparisons."""
    if value is None:
        return ""
    text = strip_accents(str(value)).strip().lower()
    return _SPACES.sub(" ", text)


def is_null_token(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and value != value:  # NaN
        return True
    return normalize_token(value) in NULL_TOKENS


# --------------------------------------------------------------------------- numbers


class NumberLocale(StrEnum):
    """How a number is written. Names follow the decimal separator, not the country."""

    POINT = "point"  # 1,234.56 (en)
    COMMA = "comma"  # 1.234,56 (es) · 1 234,56 (fr)
    PLAIN = "plain"  # 1234 / 1234.5 — no grouping, ambiguous-free


_CURRENCY = re.compile(r"(?i)\b(cop|cad|usd|eur|us|ca|col)\b|[$€£¢]")
_NUM_CHARS = re.compile(r"^[+-]?[\d.,' ]+$")


def _clean_number_text(value: str) -> tuple[str, bool]:
    text = _CURRENCY.sub("", value)
    text = _SPACES.sub(" ", text).strip()
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1].strip()
    if text.endswith("-") and not text.startswith("-"):
        negative, text = True, text[:-1].strip()
    if text.startswith(("-", "−")):
        negative, text = True, text[1:].strip()
    elif text.startswith("+"):
        text = text[1:].strip()
    return text, negative


def classify_number(value: str) -> NumberLocale | None:
    """Return the notation of ``value`` if it is unambiguous, ``PLAIN`` if it has no
    grouping, or ``None`` if it is not a number or genuinely ambiguous (e.g. ``1,234``)."""
    text, _ = _clean_number_text(value)
    if not text or not _NUM_CHARS.match(text):
        return None
    has_dot, has_comma = "." in text, "," in text
    has_space = " " in text or "'" in text
    if has_dot and has_comma:
        return NumberLocale.POINT if text.rfind(".") > text.rfind(",") else NumberLocale.COMMA
    if has_space:
        # "1 234,56" (fr) or "1 234.56" (rare) — the decimal mark decides; no mark = plain grouping.
        # Groups after the first must be exactly 3 digits, otherwise it is a phone or an id.
        groups = re.split(r"[ ']", re.split(r"[.,]", text)[0])
        if any(len(g) != 3 or not g.isdigit() for g in groups[1:]) or not groups[0].isdigit():
            return None
        if has_comma:
            return NumberLocale.COMMA
        return NumberLocale.POINT if has_dot else NumberLocale.COMMA
    if has_comma:
        head, _, tail = text.rpartition(",")
        if text.count(",") > 1:
            return NumberLocale.POINT  # 1,234,567
        if len(tail) != 3:
            return NumberLocale.COMMA  # 12,5 / 1234,56
        return None if head.isdigit() and len(head) <= 3 else NumberLocale.POINT
    if has_dot:
        head, _, tail = text.rpartition(".")
        if text.count(".") > 1:
            return NumberLocale.COMMA  # 1.234.567
        if len(tail) != 3:
            return NumberLocale.POINT  # 12.5 / 1234.56
        return None if head.isdigit() and len(head) <= 3 else NumberLocale.PLAIN
    return NumberLocale.PLAIN


def _is_ambiguous(text: str) -> bool:
    """``1,234`` / ``1.234``: one separator, ≤ 3 leading digits, exactly 3 trailing digits."""
    for sep in (",", "."):
        head, found, tail = text.partition(sep)
        if (
            found
            and sep not in tail
            and head.isdigit()
            and len(head) <= 3
            and len(tail) == 3
            and tail.isdigit()
        ):
            return True
    return False


def parse_number(value: object, locale: NumberLocale | str | None = None) -> float | None:
    """Parse a number written in EN, ES or FR notation.

    ``locale`` resolves ambiguous values such as ``1.234`` (es → 1234, en → 1.234).
    Without it, the notation is guessed per value and ambiguous values follow EN.
    """
    if value is None or is_null_token(value):
        return None
    if isinstance(value, int | float):
        return float(value)
    text, negative = _clean_number_text(str(value))
    if not text or not _NUM_CHARS.match(text):
        return None
    kind = classify_number(str(value))
    if kind is None:
        if not _is_ambiguous(text):
            return None
        kind = NumberLocale(locale) if locale else NumberLocale.POINT
    text = text.replace(" ", "").replace("'", "")
    if kind == NumberLocale.COMMA:
        text = text.replace(".", "").replace(",", ".")
    elif kind == NumberLocale.POINT:
        text = text.replace(",", "")
    try:
        number = float(text)
    except ValueError:
        return None
    return -number if negative else number


def infer_number_locale(values: Iterable[object]) -> NumberLocale | None:
    """Dominant notation among unambiguous values (PLAIN only if nothing else is seen)."""
    counts = Counter(classify_number(str(v)) for v in values if not is_null_token(v))
    counts.pop(None, None)
    plain = counts.pop(NumberLocale.PLAIN, 0)
    if counts:
        return counts.most_common(1)[0][0]
    return NumberLocale.PLAIN if plain else None


# --------------------------------------------------------------------------- dates


class DateFormat(StrEnum):
    ISO = "iso"  # 2024-03-12[T10:00[:00][.fff][Z|±hh:mm]]
    DMY = "dmy"  # 12/03/2024 (es, fr, en-GB)
    MDY = "mdy"  # 03/12/2024 (en-US)
    AMBIGUOUS = "ambiguous"  # 05/06/2024 — day and month both ≤ 12
    YMD_SLASH = "ymd_slash"  # 2024/03/12
    COMPACT = "compact"  # 20240312


_ISO = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})"
    r"(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?)?\s*"
    r"(Z|[+-]\d{2}:?\d{2})?$"
)
_SLASHED = re.compile(
    r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?$"
)
_YMD_SLASH = re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})$")
_COMPACT = re.compile(r"^(\d{4})(\d{2})(\d{2})$")

# Dates before this are placeholders (e.g. SEAO "0001-01-01T00:00:00-04:57").
MIN_PLAUSIBLE_YEAR = 1900


def classify_date(value: object) -> DateFormat | None:
    if is_null_token(value):
        return None
    text = str(value).strip()
    if _ISO.match(text):
        return DateFormat.ISO
    if _YMD_SLASH.match(text):
        return DateFormat.YMD_SLASH
    if _COMPACT.match(text):
        y, mo, d = int(text[:4]), int(text[4:6]), int(text[6:])
        return DateFormat.COMPACT if 1900 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31 else None
    m = _SLASHED.match(text)
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2))
    if a > 31 or b > 31 or (a > 12 and b > 12):
        return None
    if a > 12:
        return DateFormat.DMY
    if b > 12:
        return DateFormat.MDY
    return DateFormat.AMBIGUOUS


def _offset(text: str | None) -> timezone | None:
    if not text:
        return None
    if text == "Z":
        return UTC
    sign = -1 if text[0] == "-" else 1
    digits = text[1:].replace(":", "")
    return timezone(sign * timedelta(hours=int(digits[:2]), minutes=int(digits[2:])))


def _year(y: str) -> int:
    year = int(y)
    if len(y) == 2:
        return 2000 + year if year < 70 else 1900 + year
    return year


def parse_date(value: object, dayfirst: bool | None = None) -> datetime | None:
    """Parse ISO, dd/mm/yyyy, mm/dd/yyyy, yyyy/mm/dd and yyyymmdd.

    ``dayfirst`` resolves ambiguous slashed dates (05/06/2024); default ``True``
    because two of the three source jurisdictions write day first.
    Time-zone offsets are kept (aware datetime); placeholders before 1900 → ``None``.
    """
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if is_null_token(value):
        return None
    text = str(value).strip()
    try:
        if m := _ISO.match(text):
            y, mo, d, hh, mi, ss, frac, tz = m.groups()
            result = datetime(
                int(y),
                int(mo),
                int(d),
                int(hh or 0),
                int(mi or 0),
                int(ss or 0),
                int((frac or "0").ljust(6, "0")),
                tzinfo=_offset(tz),
            )
        elif m := _YMD_SLASH.match(text):
            result = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        elif (m := _COMPACT.match(text)) and classify_date(text) == DateFormat.COMPACT:
            result = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        elif m := _SLASHED.match(text):
            a, b, y = int(m.group(1)), int(m.group(2)), _year(m.group(3))
            kind = classify_date(text)
            if kind is None:
                return None
            first_is_day = kind == DateFormat.DMY or (
                kind == DateFormat.AMBIGUOUS and (dayfirst is None or dayfirst)
            )
            day, month = (a, b) if first_is_day else (b, a)
            result = datetime(
                y, month, day, int(m.group(4) or 0), int(m.group(5) or 0), int(m.group(6) or 0)
            )
        else:
            return None
    except ValueError:
        return None
    return result if result.year >= MIN_PLAUSIBLE_YEAR else None


def infer_dayfirst(values: Iterable[object], default: bool = True) -> bool:
    """True if unambiguous slashed values are mostly day-first."""
    counts = Counter(classify_date(v) for v in values)
    dmy, mdy = counts.get(DateFormat.DMY, 0), counts.get(DateFormat.MDY, 0)
    if dmy == mdy:
        return default
    return dmy > mdy


def date_formats(values: Iterable[object]) -> Counter[DateFormat]:
    """Histogram of date notations (nulls and unparseable values excluded)."""
    counts = Counter(classify_date(v) for v in values)
    counts.pop(None, None)
    return counts


# --------------------------------------------------------------------------- booleans

TRUE_TOKENS = frozenset({"true", "yes", "y", "si", "s", "oui", "o", "1", "verdadero", "vrai"})
FALSE_TOKENS = frozenset({"false", "no", "n", "non", "0", "falso", "faux"})


def parse_bool(value: object) -> bool | None:
    token = normalize_token(value)
    if token in TRUE_TOKENS:
        return True
    if token in FALSE_TOKENS:
        return False
    return None
