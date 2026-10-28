"""Every cleaning operation is a pure, deterministic function (slice 5b DoD)."""

import math

import pandas as pd
import pytest

from app.config import settings
from app.core.cleaning import ops
from app.core.cleaning.ops import Context, FxTable, apply_steps, output_hash

CTX = Context(FxTable.from_csv(settings.fx_path))


def frame(**cols) -> pd.DataFrame:
    return pd.DataFrame(cols, dtype=object)


def test_operations_do_not_mutate_input() -> None:
    df = frame(amount_original=["1.234,56"], signed_date=["12/03/2024"], supplier_name=[" acme "])
    snapshot = df.copy()
    apply_steps(
        df,
        [
            {"op": "parse_numbers", "args": {"column": "amount_original"}},
            {"op": "parse_dates", "args": {"column": "signed_date"}},
            {"op": "normalize_text", "args": {"column": "supplier_name", "case": "upper"}},
        ],
        CTX,
    )
    pd.testing.assert_frame_equal(df, snapshot)


def test_rename_and_drop_columns() -> None:
    df = frame(a=["1"], b=["2"])
    assert list(ops.rename_columns(df, CTX, {"a": "x", "missing": "y"}).columns) == ["x", "b"]
    assert list(ops.drop_columns(df, CTX, ["b", "missing"]).columns) == ["a"]


def test_mask_columns_is_stable() -> None:
    df = frame(email=["a@example.org", "a@example.org", "", None])
    out = ops.mask_columns(df, CTX, ["email"])
    assert out["email"][0] == out["email"][1] and out["email"][0].startswith("MASK-")
    assert out["email"][2] is None and out["email"][3] is None


def test_standardize_nulls() -> None:
    out = ops.standardize_nulls(frame(c=["N/A", "sin dato", "non disponible", "Bogotá", "-"]), CTX)
    assert out["c"].tolist()[3] == "Bogotá"
    assert (
        sum(v is None or (isinstance(v, float) and math.isnan(v)) for v in out["c"].tolist()) == 4
    )


@pytest.mark.parametrize(("keep", "expected"), [("first", ["A", "B"]), ("last", ["a ", "B"])])
def test_drop_near_duplicates(keep: str, expected: list[str]) -> None:
    df = frame(id=["A", "a ", "B"], name=["Bogotá S.A.", "BOGOTA S.A.", "X"])
    out = ops.drop_duplicates(df, CTX, mode="near", keep=keep)
    assert out["id"].tolist() == expected
    assert len(ops.drop_duplicates(df, CTX, mode="exact")) == 3
    flagged = ops.drop_duplicates(df, CTX, mode="near", keep="flag")
    assert flagged["is_duplicate"].tolist() == [False, True, False]


def test_exact_duplicates_ignore_preview_column() -> None:
    df = frame(a=["x", "x"], __row=[0, 1])
    assert len(ops.drop_duplicates(df, CTX)) == 1


@pytest.mark.parametrize(
    ("values", "notation", "expected"),
    [
        (["1.234,56", "1,234.56", "12"], "auto", [1234.56, 1234.56, 12.0]),
        (["1.234", "2.500,10"], "auto", [1234.0, 2500.10]),  # ambiguous follows dominant comma
        (["1.234"], "point", [1.234]),
        (["1.234"], "comma", [1234.0]),
        (["N/A", None], "auto", [None, None]),
    ],
)
def test_parse_numbers(values, notation: str, expected) -> None:
    out = ops.parse_numbers(frame(amount=values), CTX, "amount", notation)["amount"].tolist()
    got = [None if math.isnan(v) else round(v, 3) for v in out]
    assert got == expected


def test_parse_dates_dayfirst_and_timezone() -> None:
    df = frame(d=["05/06/2024", "2024-06-07T23:30:00-05:00", "N/A"])
    out = ops.parse_dates(df, CTX, "d", dayfirst=True, timezone="utc")["d"].tolist()
    assert out[0] == pd.Timestamp("2024-06-05")
    assert out[1] == pd.Timestamp("2024-06-08T04:30:00")
    assert pd.isna(out[2])
    local = ops.parse_dates(df, CTX, "d", dayfirst=False, timezone="drop")["d"].tolist()
    assert local[0] == pd.Timestamp("2024-05-06") and local[1] == pd.Timestamp(
        "2024-06-07T23:30:00"
    )


def test_normalize_timezones() -> None:
    out = ops.normalize_timezones(
        frame(d=["2026-05-01T00:00:00-04:00", "01/05/2026"]), CTX, "d", "utc"
    )
    assert out["d"].tolist() == ["2026-05-01T04:00:00", "01/05/2026"]


def test_convert_currency_uses_month_rate() -> None:
    df = frame(
        amount_original=["100", "100", "100"],
        currency=["USD", "CAD", "XXX"],
        signed_date=["2025-03-10"] * 3,
    )
    out = ops.convert_currency(df, CTX, to="CAD")
    usd = CTX.fx.cad_per_unit("USD", "2025-03")
    assert out["amount_original"].tolist()[:2] == [round(100 * usd, 2), 100.0]
    assert math.isnan(out["amount_original"].tolist()[2])  # unknown currency → not converted
    assert out["currency"].tolist()[:2] == ["CAD", "CAD"]
    added = ops.convert_currency(df, CTX, to="CAD", mode="add_column")
    assert added["amount_original"].tolist() == ["100", "100", "100"] and "amount_cad" in added


def test_fx_outside_table_uses_nearest_month() -> None:
    first = min(CTX.fx.rates["USD"])
    assert CTX.fx.cad_per_unit("USD", "1999-01") == CTX.fx.rates["USD"][first]


def test_normalize_text_and_unify_variants() -> None:
    df = frame(n=["  Bogotá  S.A.", "BOGOTA S.A.", "Bogotá S.A.", "Bogotá S.A.", None])
    upper = ops.normalize_text(df, CTX, "n", case="upper", remove_accents=True)["n"].tolist()
    assert upper[:4] == ["BOGOTA S.A."] * 4 and upper[4] is None
    unified = ops.unify_variants(df, CTX, "n")["n"].tolist()
    assert unified[:4] == ["Bogotá S.A."] * 4


@pytest.mark.parametrize(
    ("action", "rows", "extra"),
    [("drop_rows", 2, None), ("flag", 3, "c_missing"), ("keep", 3, None)],
)
def test_handle_missing(action: str, rows: int, extra) -> None:
    out = ops.handle_missing(frame(c=["a", None, "b"]), CTX, "c", action)
    assert len(out) == rows and (extra is None or extra in out.columns)
    filled = ops.handle_missing(frame(c=["a", "N/A"]), CTX, "c", "fill", "unknown")
    assert filled["c"].tolist() == ["a", "unknown"]


def test_handle_outliers() -> None:
    values = [str(1000 + i * 10) for i in range(40)] + ["99999999"]
    flagged = ops.handle_outliers(frame(a=values), CTX, "a", "flag")
    assert flagged["a_outlier"].tolist()[-1] is True and sum(flagged["a_outlier"]) == 1
    capped = ops.handle_outliers(frame(a=values), CTX, "a", "cap")["a"].tolist()
    assert capped[-1] < 99999999 and capped[0] == 1000.0
    assert ops.handle_outliers(frame(a=values), CTX, "a", "keep")["a"].tolist() == values


def test_cast_type() -> None:
    df = frame(n=["1", "2.0", None, "x"])
    assert ops.cast_type(df, CTX, "n", "integer")["n"].tolist()[:2] == [1, 2]
    assert ops.cast_type(df, CTX, "n", "string")["n"].tolist()[0] == "1"


def test_standardize_categories_keeps_source() -> None:
    df = frame(award_type=["Contratación directa", "TN", "open", "Licitación pública", "something"])
    out = ops.standardize_categories(df, CTX, "award_type")
    assert out["award_type"].tolist() == ["direct", "direct", "open", "open", "other"]
    assert out["award_type_source"].tolist()[0] == "Contratación directa"


def test_output_hash_is_deterministic() -> None:
    df = frame(a=["1", None], b=[1.5, float("nan")])
    assert output_hash(df) == output_hash(df.copy())
    assert output_hash(df) != output_hash(frame(a=["1", None], b=[1.5, 2.0]))
