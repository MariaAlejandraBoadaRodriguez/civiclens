"""Detectors, recipe validation/replay and code export (slice 5b DoD)."""

import json
import subprocess
import sys
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from app.config import settings
from app.core.cleaning.codegen import pandas_preview, pandas_script, sql_script
from app.core.cleaning.detectors import ISSUE_TYPES, detect_issues, recommended_steps
from app.core.cleaning.ops import OPERATIONS, Context, FxTable
from app.core.cleaning.recipe import RecipeError, document, replay, validate_steps
from app.core.profile.profiler import profile_frame
from app.i18n.loader import catalog

CTX = Context(FxTable.from_csv(settings.fx_path))


def dirty_frame() -> pd.DataFrame:
    """Small staged frame (canonical names) with one instance of every issue type."""
    n = 60
    rows = []
    for i in range(n):
        rows.append(
            {
                "contract_id": f"C-{i}",
                "entity_name": "Alcaldía de Bogotá" if i % 7 else "ALCALDIA DE BOGOTA",
                "supplier_name": f"Proveedor {i % 9} S.A.S."
                if i % 11
                else f"PROVEEDOR {i % 9} S.A.S.",
                "signed_date": f"{(i % 27) + 1:02d}/03/2025"
                if i % 3
                else f"2025-03-{(i % 27) + 1:02d}T10:00:00-05:00",
                "amount_original": (f"{1000 + i},50" if i % 4 else f"{1000 + i}.50")
                if i != 5
                else "9999999999,00",
                "currency": "USD" if i % 10 == 0 else "COP",
                "award_type": "Contratación directa" if i % 2 else "Licitación pública",
                "n_bidders": str(i % 4) if i % 13 else "N/A",
                "city": "sin dato" if i % 9 == 0 else "Bogotá",
                "email_contacto": f"persona{i}@example.org",
            }
        )
    rows.append(dict(rows[1]))  # exact duplicate
    return pd.DataFrame(rows, dtype=object)


@pytest.fixture(scope="module")
def issues():
    df = dirty_frame()
    return detect_issues(df, profile_frame(df), CTX, "COP")


def test_every_issue_type_is_detected(issues) -> None:
    found = {i.issue_type for i in issues}
    expected = set(ISSUE_TYPES) - {
        "header_mapping"
    }  # covered by the seed test in test_cleaning_api
    assert expected <= found, expected - found


def test_issue_catalogs_complete_in_en_and_es(issues) -> None:
    """DoD: every issue type has EN + ES title/what/why/learn_more and option texts."""
    for lang in ("en", "es"):
        cat = catalog(lang)
        for kind in ISSUE_TYPES:
            for part in ("title", "what", "why", "learn_more"):
                assert f"issues.{kind}.{part}" in cat, (lang, kind, part)
        for issue in issues:
            for opt in issue.options:
                key = "use" if opt.option_id.startswith("use_") else opt.option_id
                assert f"issues.{issue.issue_type}.options.{key}.label" in cat, (
                    lang,
                    issue.issue_type,
                    key,
                )
                assert f"issues.{issue.issue_type}.options.{key}.hint" in cat
        for op in OPERATIONS:
            assert f"recipes.ops.{op}" in cat


def test_every_issue_has_one_recommended_option_and_previews(issues) -> None:
    for issue in issues:
        assert sum(o.recommended for o in issue.options) == 1, issue.issue_type
        for opt in issue.options:
            assert len(issue.preview_after.get(opt.option_id, issue.preview_before)) == len(
                issue.preview_before
            )
    currency = next(i for i in issues if i.issue_type == "mixed_currency")
    assert currency.kpi_before["value"] is None  # mixed currencies: not comparable
    assert currency.kpi_after["to_cad"]["currency"] == "CAD"
    dates = next(i for i in issues if i.issue_type == "date_format")
    assert dates.kpi_after["day_first"]["value"] == 1.0 > dates.kpi_before["value"]


def test_recommended_recipe_replays_identically(issues) -> None:
    """DoD: same recipe + input → identical output hash."""
    steps = recommended_steps(issues)
    df = dirty_frame()
    first, stats, h1 = replay(df, steps, CTX)
    second, _, h2 = replay(df.copy(), json.loads(json.dumps(steps)), CTX)
    assert h1 == h2
    assert len(first) == len(df) - 1  # the duplicate is gone
    assert [s.op for s in stats] == [s["op"] for s in steps]
    q_before, q_after = profile_frame(df)["quality"], profile_frame(first)["quality"]
    assert q_after["consistency"] > q_before["consistency"]
    assert q_after["uniqueness"] > q_before["uniqueness"]


def test_exported_pandas_script_reproduces_output(issues, tmp_path: Path) -> None:
    """DoD: the exported pandas script reproduces the output (same SHA-256)."""
    steps = recommended_steps(issues)
    df = dirty_frame()
    _, _, expected = replay(df, steps, CTX)
    staged = tmp_path / "staged.parquet"
    df.astype("string").to_parquet(staged, index=False)
    script = tmp_path / "clean.py"
    script.write_text(pandas_script(document("test", steps)), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(script),
            str(staged),
            str(settings.fx_path),
            str(tmp_path / "out.csv"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == expected


def test_exported_sql_runs_on_duckdb(issues, tmp_path: Path) -> None:
    steps = recommended_steps(issues)
    df = dirty_frame()
    clean, _, _ = replay(df, steps, CTX)
    staged = tmp_path / "staged.parquet"
    df.astype("string").to_parquet(staged, index=False)
    con = duckdb.connect()
    con.execute(f"CREATE VIEW staged AS SELECT * FROM '{staged}'")
    con.execute(f"CREATE VIEW fx_rates AS SELECT * FROM read_csv('{settings.fx_path}')")
    out = con.execute(sql_script(document("t", steps), list(df.columns))).df()
    assert len(out) == len(clean)
    assert set(out["award_type"].dropna()) <= {"direct", "open", "limited", "other"}
    assert out["email_contacto"].str.startswith("MASK-").all()


def test_preview_code_lists_every_step(issues) -> None:
    steps = recommended_steps(issues)
    code = pandas_preview(steps)
    for step in steps:
        assert f"{step['op']}(df, ctx" in code


@pytest.mark.parametrize(
    "steps",
    [
        "not a list",
        [{"args": {}}],
        [{"op": "rm_rf", "args": {}}],
        [{"op": "parse_numbers", "args": {}}],  # missing column
        [{"op": "parse_numbers", "args": {"column": "a", "evil": 1}}],
        [{"op": "parse_numbers", "args": ["a"]}],
    ],
)
def test_invalid_recipes_are_rejected(steps) -> None:
    with pytest.raises(RecipeError):
        validate_steps(steps)


def test_replay_reports_missing_column() -> None:
    with pytest.raises(RecipeError) as exc:
        replay(
            pd.DataFrame({"a": ["1"]}, dtype=object),
            [{"op": "parse_numbers", "args": {"column": "b"}}],
            CTX,
        )
    assert exc.value.step == 0
