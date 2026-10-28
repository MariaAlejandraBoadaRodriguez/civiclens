"""Cleaning Studio API: issues, recipes, replay jobs and exports (seed A = SECOP)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(scope="module")
def secop_issues() -> dict:
    r = client.get("/api/v1/datasets/secop_co/issues", headers={"Accept-Language": "en"})
    assert r.status_code == 200, r.text
    return r.json()


def test_seed_a_has_the_expected_issue_types(secop_issues: dict) -> None:
    types = [i["issue_type"] for i in secop_issues["issues"]]
    for kind in (
        "header_mapping",
        "pii",
        "duplicates",
        "missing_values",
        "date_format",
        "number_locale",
        "mixed_currency",
        "text_variants",
        "category_labels",
        "outliers",
    ):
        assert kind in types, kind
    first = secop_issues["issues"][0]
    assert first["position"] == 1 and first["of"] == len(types)


def test_issues_have_identical_machine_fields_in_en_and_es(secop_issues: dict) -> None:
    es = client.get("/api/v1/datasets/secop_co/issues", headers={"Accept-Language": "es"}).json()
    machine = (
        "issue_id",
        "issue_type",
        "category",
        "field",
        "affected_rows",
        "preview_before",
        "kpi_before",
    )
    for a, b in zip(secop_issues["issues"], es["issues"], strict=True):
        assert {k: a[k] for k in machine} == {k: b[k] for k in machine}
        assert [o["option_id"] for o in a["options"]] == [o["option_id"] for o in b["options"]]
        assert a["title"] != b["title"] and a["why"] != b["why"]
    currency_en = next(i for i in secop_issues["issues"] if i["issue_type"] == "mixed_currency")
    currency_es = next(i for i in es["issues"] if i["issue_type"] == "mixed_currency")
    assert currency_en["title"] == "Amounts are in 3 different currencies"
    assert currency_es["title"] == "Los montos están en 3 monedas distintas"
    assert currency_en["options"][0]["label"] == "Convert all to CAD"
    assert currency_es["options"][0]["label"] == "Convertir todo a CAD"
    assert "TRM" in currency_en["fx_note"]


def test_save_apply_and_export_recipe(secop_issues: dict) -> None:
    """DoD: a recipe saved from the recommended options replays identically."""
    steps = [
        s
        for i in secop_issues["issues"]
        for o in i["options"]
        if o["recommended"]
        for s in o["steps"]
    ]
    r = client.post("/api/v1/recipes", json={"name": "secop monthly", "steps": steps})
    assert r.status_code == 201, r.text
    recipe = r.json()
    assert recipe["version"] == 1
    again = client.post("/api/v1/recipes", json={"name": "secop monthly", "steps": steps}).json()
    assert again["version"] == 2

    hashes = []
    for _ in range(2):
        job = client.post(
            "/api/v1/datasets/secop_co/recipes/apply", json={"recipe_id": recipe["id"]}
        )
        assert job.status_code == 202
        result = client.get(job.headers["location"]).json()
        assert result["status"] == "succeeded", result
        hashes.append(result["result"]["output_hash"])
    assert hashes[0] == hashes[1]
    res = result["result"]
    assert res["rows_after"] < res["rows_before"]
    assert res["quality_after"]["score"] > res["quality_before"]["score"]
    assert res["quality_after"]["consistency"] > res["quality_before"]["consistency"]
    after = client.get("/api/v1/datasets/secop_co/issues").json()
    assert after["quality_after"] == res["quality_after"]

    script = client.get(f"/api/v1/recipes/{recipe['id']}/export?format=pandas")
    assert script.status_code == 200 and "def main(" in script.text
    assert "attachment" in script.headers["content-disposition"]
    sql = client.get(f"/api/v1/recipes/{recipe['id']}/export?format=sql").text
    assert sql.startswith("-- CivicLens cleaning recipe") and "fx_rates" in sql
    doc = client.get(f"/api/v1/recipes/{recipe['id']}/export?format=json").json()
    assert doc["schema"] == "civiclens.recipe/v1" and doc["steps"] == steps


def test_inline_recipe_and_preview() -> None:
    steps = [
        {"op": "standardize_nulls", "args": {}},
        {"op": "parse_numbers", "args": {"column": "amount_original"}},
    ]
    preview = client.post(
        "/api/v1/recipes/preview", json={"steps": steps, "columns": ["amount_original"]}
    ).json()
    assert set(preview) == {"pandas", "sql", "json"}
    assert "parse_numbers(df, ctx, column='amount_original')" in preview["pandas"]
    job = client.post(
        "/api/v1/datasets/contracts_qc/recipes/apply",
        json={"recipe": {"name": "x", "steps": steps}},
    )
    assert client.get(job.headers["location"]).json()["status"] == "succeeded"


def test_invalid_recipe_is_a_localized_422() -> None:
    r = client.post(
        "/api/v1/recipes",
        json={"name": "bad", "steps": [{"op": "drop_table", "args": {}}]},
        headers={"Accept-Language": "es"},
    )
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "recipe.invalid" and body["title"] == "La receta no es válida"
    assert body["params"]["step"] == 1


def test_recipe_with_missing_column_fails_job_with_code() -> None:
    steps = [{"op": "parse_numbers", "args": {"column": "does_not_exist"}}]
    job = client.post(
        "/api/v1/datasets/contracts_ca/recipes/apply",
        json={"recipe": {"name": "x", "steps": steps}},
    )
    result = client.get(job.headers["location"]).json()
    assert result["status"] == "failed" and result["error"]["code"] == "recipe.invalid"


def test_unknown_recipe_404() -> None:
    assert client.get("/api/v1/recipes/nope").json()["code"] == "recipe.not_found"
