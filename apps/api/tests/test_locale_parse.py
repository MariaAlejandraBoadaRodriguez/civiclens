"""Locale-aware parsing (slice 5a DoD: 30+ parser tests)."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.core.ingest.locale_parse import (
    DateFormat,
    NumberLocale,
    classify_date,
    classify_number,
    date_formats,
    infer_dayfirst,
    infer_number_locale,
    is_null_token,
    parse_bool,
    parse_date,
    parse_number,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.234,56", 1234.56),  # es
        ("1,234.56", 1234.56),  # en
        ("1 234,56", 1234.56),  # fr, regular space
        ("1 234,56", 1234.56),  # fr, narrow no-break space
        ("1 234 567,89", 1234567.89),  # fr, no-break spaces
        ("1.234.567", 1234567.0),  # es grouping, no decimals
        ("1,234,567", 1234567.0),  # en grouping, no decimals
        ("3700000", 3700000.0),
        ("12,5", 12.5),
        ("12.5", 12.5),
        ("0,75", 0.75),
        ("-1.234,56", -1234.56),
        ("(1,234.56)", -1234.56),  # accounting negative
        ("1.234,56-", -1234.56),  # trailing minus (SAP exports)
        ("$1,234.56", 1234.56),
        ("COP 1.250.000.000", 1250000000.0),
        ("1.250.000.000,00 COP", 1250000000.0),
        ("CAD 48,500.00", 48500.0),
        ("+42", 42.0),
        ("1'234.50", 1234.5),  # Swiss-style apostrophe grouping
    ],
)
def test_parse_number(raw: str, expected: float) -> None:
    assert parse_number(raw) == pytest.approx(expected)


@pytest.mark.parametrize(
    "raw", ["", "N/A", "-", "sin dato", "non disponible", "abc", "12-34-56", None]
)
def test_parse_number_rejects(raw) -> None:
    assert parse_number(raw) is None


def test_phone_is_not_a_number() -> None:
    assert parse_number("+57 300 555 0123") is None


@pytest.mark.parametrize(
    ("raw", "locale", "expected"),
    [
        ("1.234", "comma", 1234.0),
        ("1.234", "point", 1.234),
        ("1,234", "comma", 1.234),
        ("1,234", "point", 1234.0),
    ],
)
def test_ambiguous_numbers_follow_locale(raw: str, locale: str, expected: float) -> None:
    assert parse_number(raw, locale) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("raw", "kind"),
    [
        ("1.234,56", NumberLocale.COMMA),
        ("1,234.56", NumberLocale.POINT),
        ("1 234,56", NumberLocale.COMMA),
        ("1234", NumberLocale.PLAIN),
        ("1.234", None),
        ("1,234", None),
        ("hello", None),
    ],
)
def test_classify_number(raw: str, kind) -> None:
    assert classify_number(raw) == kind


def test_infer_number_locale_ignores_ambiguous_values() -> None:
    assert infer_number_locale(["1.234", "1.234.567,89", "12,5", "N/A"]) == NumberLocale.COMMA
    assert infer_number_locale(["1,234.5", "1,234"]) == NumberLocale.POINT
    assert infer_number_locale(["12", "13"]) == NumberLocale.PLAIN
    assert infer_number_locale(["", "-"]) is None


@pytest.mark.parametrize(
    ("raw", "dayfirst", "expected"),
    [
        ("12/03/2024", True, datetime(2024, 3, 12)),  # ES reading
        ("12/03/2024", False, datetime(2024, 12, 3)),  # EN-US reading
        ("25/12/2024", None, datetime(2024, 12, 25)),  # unambiguous day-first
        ("12/25/2024", None, datetime(2024, 12, 25)),  # unambiguous month-first
        ("2024-03-12", None, datetime(2024, 3, 12)),
        ("2024/03/12", None, datetime(2024, 3, 12)),
        ("20240312", None, datetime(2024, 3, 12)),
        ("12.03.2024", True, datetime(2024, 3, 12)),
        ("12-03-24", True, datetime(2024, 3, 12)),
        ("5/6/99", True, datetime(1999, 6, 5)),
        ("2025-03-03T19:13:06.908", None, datetime(2025, 3, 3, 19, 13, 6, 908000)),
        ("12/03/2024 14:30", True, datetime(2024, 3, 12, 14, 30)),
    ],
)
def test_parse_date(raw: str, dayfirst, expected: datetime) -> None:
    assert parse_date(raw, dayfirst=dayfirst) == expected


def test_parse_date_keeps_time_zone() -> None:
    value = parse_date("2026-05-01T00:00:00-04:00")
    assert value.utcoffset() == timedelta(hours=-4)
    assert value.astimezone(UTC) == datetime(2026, 5, 1, 4, 0, tzinfo=UTC)
    assert parse_date("2024-01-01T10:00:00Z").tzinfo == UTC
    assert parse_date("2024-01-01T10:00:00+0530").utcoffset() == timezone(
        timedelta(hours=5, minutes=30)
    ).utcoffset(None)


@pytest.mark.parametrize(
    "raw", ["0001-01-01T00:00:00-04:57", "31/02/2024", "2024-13-01", "", "sin dato", "hello"]
)
def test_parse_date_rejects(raw: str) -> None:
    assert parse_date(raw) is None


@pytest.mark.parametrize(
    ("raw", "fmt"),
    [
        ("2024-03-12", DateFormat.ISO),
        ("25/12/2024", DateFormat.DMY),
        ("12/25/2024", DateFormat.MDY),
        ("05/06/2024", DateFormat.AMBIGUOUS),
        ("20240312", DateFormat.COMPACT),
        ("20168806", None),  # an id that looks like yyyymmdd but has month 88
    ],
)
def test_classify_date(raw: str, fmt) -> None:
    assert classify_date(raw) == fmt


def test_infer_dayfirst() -> None:
    assert infer_dayfirst(["25/12/2024", "13/01/2024", "05/06/2024"]) is True
    assert infer_dayfirst(["12/25/2024", "01/13/2024"]) is False
    assert infer_dayfirst(["05/06/2024"], default=False) is False


def test_date_formats_histogram() -> None:
    assert date_formats(["2024-01-01", "25/12/2024", "N/A", "x"]) == {
        DateFormat.ISO: 1,
        DateFormat.DMY: 1,
    }


@pytest.mark.parametrize(
    "token",
    [
        "",
        " ",
        "N/A",
        "n/a",
        "NA",
        "-",
        "--",
        "null",
        "None",
        "sin dato",
        "Sin Dato",
        "No Definido",
        "no aplica",
        "non disponible",
        "Non Disponible",
        "N.D.",
        "S.O.",
        "Sin información",
    ],
)
def test_null_tokens(token: str) -> None:
    assert is_null_token(token)


@pytest.mark.parametrize("value", ["0", "Bogotá", "NIT", "nadie", "2024"])
def test_not_null_tokens(value: str) -> None:
    assert not is_null_token(value)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Sí", True),
        ("si", True),
        ("Oui", True),
        ("Yes", True),
        ("No", False),
        ("Non", False),
        ("0", False),
        ("maybe", None),
    ],
)
def test_parse_bool(raw: str, expected) -> None:
    assert parse_bool(raw) is expected
