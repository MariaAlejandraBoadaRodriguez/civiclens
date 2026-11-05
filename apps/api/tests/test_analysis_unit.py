"""Unit tests of the generic analysis core: typing, generated questions and the pack engine."""

from __future__ import annotations

import duckdb
import pandas as pd
import pytest

from app.core import packs
from app.core.analysis.questions import generate, pick, positive_expr, year_like
from app.core.analysis.table import build_table, for_duckdb, safe_name
from app.core.profile.pii import PiiKind, detect_pii


def _frame() -> pd.DataFrame:
    n = 60
    return pd.DataFrame(
        {
            "Client ID": [f"C{i:04d}" for i in range(n)],
            "Région": [["Norte", "Sur", "Este"][i % 3] for i in range(n)],
            "Amount (€)": [f"{1000 + i * 37},50" for i in range(n)],  # decimal comma
            "Signed": [f"{1 + i % 28:02d}/{1 + i % 12:02d}/2024" for i in range(n)],  # day first
            "default": ["sí" if i % 5 == 0 else "no" for i in range(n)],
            "Altitude": [835 if i % 2 else 959 for i in range(n)],
            "Founded": [1784 + i for i in range(n)],
            "Notes": [f"free text number {i} " * 4 for i in range(n)],
        }
    )


def test_build_table_types_names_and_locales() -> None:
    typed, metas = build_table(_frame())
    kinds = {m.name: m.kind for m in metas}
    assert kinds == {
        "client_id": "identifier",
        "region": "category",
        "amount": "number",
        "signed": "date",
        "default": "boolean",
        "altitude": "integer",
        "founded": "integer",
        "notes": "text",
    }
    by = {m.name: m for m in metas}
    assert by["amount"].min == pytest.approx(1000.5)  # "1000,50" parsed with the comma locale
    assert by["signed"].max.startswith("2024-12")  # 13/12/2024 is read day first
    assert by["default"].binary and by["altitude"].binary  # two values each
    assert by["region"].source == "Région" and by["region"].top[0]["count"] == 20
    con = duckdb.connect()
    con.register("d", for_duckdb(typed, metas))
    assert con.sql('SELECT COUNT(*) FROM d WHERE "default"').fetchall()[0][0] == 12


def test_safe_names_are_unique_and_never_start_with_a_digit() -> None:
    taken: set[str] = set()
    assert [safe_name(h, taken) for h in ("emp.var.rate", "2024", "Ñandú", "", "a", "a")] == [
        "emp_var_rate",
        "c_2024",
        "nandu",
        "column",
        "a",
        "a_2",
    ]


def test_pick_targets_flags_not_measurements_and_skips_years() -> None:
    _, metas = build_table(_frame())
    p = pick(metas)
    assert p.target is not None and p.target.name == "default"
    assert [m.name for m in p.numbers] == ["amount"]  # not altitude (2 values), not founded
    assert year_like(next(m for m in metas if m.name == "founded"))
    assert positive_expr(p.target) == '"default" = TRUE'


def test_generated_questions_run_on_the_table() -> None:
    typed, metas = build_table(_frame())
    con = duckdb.connect()
    con.register("data", for_duckdb(typed, metas))
    questions = generate(metas, len(typed))
    kinds = {q.kind for q in questions}
    assert {"completeness", "category_counts", "target_rate", "numeric_summary"} <= kinds
    assert {"time_trend", "outliers", "identifier_duplicates"} <= kinds
    for q in questions:
        assert con.sql(q.sql).fetchall(), q.query_id
    dup = next(q for q in questions if q.kind == "identifier_duplicates")
    assert con.sql(dup.sql).fetchall()[0][2] == 0  # one summary row, even with no repeats


def test_reserved_words_and_quotes_are_quoted() -> None:
    frame = pd.DataFrame({'sel"ect': ["a", "b"] * 10, "order": list(range(20))})
    typed, metas = build_table(frame)
    con = duckdb.connect()
    con.register("data", for_duckdb(typed, metas))
    for q in generate(metas, 20):
        con.sql(q.sql).fetchall()


# ------------------------------------------------------------------------------ packs


def test_packs_load_in_order_with_general_last() -> None:
    ids = list(packs.packs())
    assert ids[0] == "government" and ids[-1] == "general" and "banking" in ids
    assert packs.packs()["banking"].default_goal == "credit_risk"


def test_role_matching_confidence_levels() -> None:
    _, metas = build_table(_frame())
    by = {m.name: m for m in metas}
    banking = packs.packs()["banking"]
    flag = banking.role("default_flag")
    assert packs.match_confidence(flag, by["default"]) == 0.95  # exact synonym
    assert packs.match_confidence(flag, by["amount"]) == 0.0  # wrong kind
    assert 0 < packs.match_confidence(banking.role("loan_amount"), by["amount"]) <= 0.95


def test_render_fills_roles_alternatives_and_positive_values() -> None:
    _, metas = build_table(_frame())
    by = {m.name: m for m in metas}
    roles = {"default_flag": {"column": "default", "positive": "True"}, "balance": {}}
    roles["loan_amount"] = {"column": "amount"}
    sql = packs.render("SELECT {balance|loan_amount}, {positive:default_flag}", roles, by)
    assert sql == 'SELECT "amount", "default" = TRUE'
    with pytest.raises(packs.MissingRole):
        packs.render("SELECT {income}", roles, by)
    assert packs.requires_ok({"requires": ["loan_amount"]}, roles, by)
    assert not packs.requires_ok({"requires_any": ["income", "balance"]}, roles, by)


def test_guess_positive_prefers_yes_words_then_the_minority() -> None:
    _, metas = build_table(pd.DataFrame({"y": ["yes"] * 3 + ["no"] * 7, "r": [0] * 3 + [1] * 7}))
    by = {m.name: m for m in metas}
    assert packs.guess_positive(by["y"]) == "True"  # yes/no became a boolean
    assert packs.guess_positive(by["r"]) == "0"  # minority: 3 of 10


def test_banking_needs_a_credit_signal_not_just_amounts() -> None:
    sales = pd.DataFrame(
        {"product": ["a", "b", "c"] * 20, "sales_amount": [float(i) for i in range(60)]}
    )
    _, metas = build_table(sales)
    scores = {s["pack"]: s["score"] for s in packs.suggestions(metas)}
    assert scores["banking"] == 0.0 and scores["general"] == 0.3


# ------------------------------------------------------------------------------ PII


def test_budget_amounts_are_not_phone_numbers() -> None:
    amounts = ["7548345900.00", "1739786250.00", "5442786808.00", "3499838774.50"]
    assert detect_pii("apropiacion_vigente", amounts) is None
    assert detect_pii("telefono", ["514.555.1234", "300-123-4567"]) == PiiKind.PHONE


def test_whole_numbers_show_without_decimals_and_their_positive_value_matches() -> None:
    """A 0/1 target with a gap is read as floats; its values must still read 0 and 1, so the
    guessed positive value compares equal to the BIGINT column in SQL."""
    frame = pd.DataFrame({"risk": [0.0] * 3 + [1.0] * 7 + [None], "n": [24.0] * 11})
    typed, metas = build_table(frame)
    by = {m.name: m for m in metas}
    assert by["n"].examples == ["24"] and {t["value"] for t in by["risk"].top} == {"0", "1"}
    positive = packs.guess_positive(by["risk"])
    assert positive == "0"
    con = duckdb.connect()
    con.register("d", for_duckdb(typed, metas))
    sql = f"SELECT COUNT(*) FROM d WHERE {positive_expr(by['risk'], positive)}"
    assert con.sql(sql).fetchall()[0][0] == 3
