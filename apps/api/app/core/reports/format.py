"""Numbers, money, percentages and months in the report language (UI language, never the data
language): en → 1,234.5 · es → 1.234,5 (as the web app's en-CA / es-CO formats)."""

from __future__ import annotations

MONTHS = {
    "en": "January February March April May June July August September October November December",
    "es": (
        "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre"
    ),
}


def number(value: float | int, lang: str, decimals: int = 0) -> str:
    text = f"{value:,.{decimals}f}"
    if lang == "es":
        text = text.replace(",", "\0").replace(".", ",").replace("\0", ".")
    return text


def compact(value: float, lang: str) -> str:
    """1.5B / 1.495,9 M: short amounts for tiles and chart labels."""
    # Spanish has no short word for 10^9 in this sense ("billón" is 10^12): millions instead.
    units = [(1e9, "B"), (1e6, "M"), (1e3, "k")] if lang == "en" else [(1e6, " M"), (1e3, " k")]
    for size, suffix in units:
        if abs(value) >= size:
            return number(value / size, lang, 1) + suffix
    return number(value, lang, 0)


def money(value: float, currency: str, lang: str, short: bool = False) -> str:
    return f"{currency} {compact(value, lang) if short else number(value, lang, 0)}"


def percent(ratio: float, lang: str, decimals: int = 1) -> str:
    text = number(ratio * 100, lang, decimals)
    return f"{text} %" if lang == "es" else f"{text}%"


def month(iso_month: str, lang: str, short: bool = False) -> str:
    """'2025-03' → 'March 2025' / 'marzo 2025' (or 'Mar 2025' / 'mar 2025')."""
    year, m = iso_month[:4], int(iso_month[5:7])
    name = MONTHS.get(lang, MONTHS["en"]).split()[m - 1]
    return f"{name[:3]} {year}" if short else f"{name} {year}"
