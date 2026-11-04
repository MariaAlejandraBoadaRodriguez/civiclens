"""Any tabular file works end to end in the SQL Lab (owner requirement: generic analysis is the
core; procurement is one domain pack). Every acceptance fixture in ``data/fixtures`` must give a
typed ``data`` table, generated questions that run and return rows, KPIs with values, a domain
suggestion, and never a 500 — procurement-only views answer 409 with a clear message."""

from __future__ import annotations

import io
import zipfile
from functools import cache
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
FIXTURES = Path(__file__).resolve().parents[3] / "data" / "fixtures"
CASES = {
    # file: (suggested pack, columns that must be typed with this kind)
    "bank_marketing.csv": ("general", {"age": "integer", "job": "category", "y": "boolean"}),
    "german_credit.csv": ("banking", {"amount": "integer", "credit_risk": "boolean"}),
    "air_quality_bucaramanga.csv": ("general", {}),
    "us_presidential_results.csv": ("general", {}),
    "budget_colombia_pgn.csv": ("general", {}),
    "sales_adventureworks.xlsx": ("general", {}),
    "sp500_companies.json": ("general", {}),
}


@cache
def uploaded(name: str) -> str:
    body = (FIXTURES / name).read_bytes()
    r = client.post("/api/v1/datasets", files={"file": (name, body, "application/octet-stream")})
    assert r.status_code == 202, r.text
    job = client.get(r.headers["location"]).json()
    assert job["status"] == "succeeded", job
    return r.json()["dataset"]["id"]


@pytest.mark.parametrize("name", sorted(CASES))
def test_sql_lab_works_for_any_dataset(name: str) -> None:
    ds = uploaded(name)
    pack, kinds = CASES[name]

    schema = client.get(f"/api/v1/datasets/{ds}/schema").json()
    assert [t["name"] for t in schema["tables"]] == ["data"]  # no empty star schema
    data = schema["tables"][0]
    assert data["role"] == "data" and data["rows"] > 100
    columns = {c["name"]: c for c in schema["data_columns"]}
    assert len(columns) >= 3 and all(c["examples"] or c["nulls"] for c in columns.values())
    for column, kind in kinds.items():
        assert columns[column]["kind"] == kind, (column, columns[column])
    assert schema["domain"]["pack"] == pack and not schema["domain"]["confirmed"]

    guided = client.get(f"/api/v1/guided-queries?dataset_id={ds}").json()["items"]
    assert len(guided) >= 5
    assert not any(g["source"] == "government" for g in guided)  # no supplier questions
    for g in guided:
        assert g["title"] and g["question"] and g["explanation"]
        assert "{" not in g["title"] + g["question"] + g["explanation"], g  # all params filled
        r = client.post("/api/v1/query", json={"dataset_id": ds, "sql": g["sql"]})
        assert r.status_code == 200, (g["query_id"], r.text)
        assert r.json()["rows"], g["query_id"]

    kpis = client.get(f"/api/v1/kpis/{ds}").json()["items"]
    assert len(kpis) >= 5 and all(k["value"] is not None for k in kpis)
    assert all("{" not in k["name"] for k in kpis)


@pytest.mark.parametrize("name", sorted(CASES))
def test_procurement_only_views_answer_409_not_500(name: str) -> None:
    ds = uploaded(name)
    for path in (
        f"/api/v1/dashboard?dataset_id={ds}",
        f"/api/v1/reports/{ds}",
        f"/api/v1/models/red_flags/latest?dataset_id={ds}",
    ):
        r = client.get(path, headers={"Accept-Language": "es"})
        assert r.status_code == 409, (path, r.text)
        assert r.json()["code"] == "domain.procurement_only"
        assert "SQL Lab" in r.json()["detail"]
    r = client.post("/api/v1/models/forecast/run", json={"dataset_id": ds})
    assert r.status_code == 409


def test_bi_export_has_the_data_table_for_any_dataset() -> None:
    ds = uploaded("bank_marketing.csv")
    r = client.get(f"/api/v1/datasets/{ds}/export?format=csv")
    assert r.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert "data.csv" in names and "fact_contract.csv" not in names


def test_spanish_texts_for_generated_questions() -> None:
    ds = uploaded("bank_marketing.csv")
    es = client.get(
        f"/api/v1/guided-queries?dataset_id={ds}", headers={"Accept-Language": "es"}
    ).json()["items"]
    en = client.get(f"/api/v1/guided-queries?dataset_id={ds}").json()["items"]
    assert [g["sql"] for g in es] == [g["sql"] for g in en]
    assert es[0]["title"] != en[0]["title"]
    rate = next(g for g in es if g["query_id"].startswith("rate_y_by_"))
    assert rate["title"].startswith("Tasa de y por ")


def test_procurement_seed_keeps_star_schema_and_its_questions() -> None:
    schema = client.get("/api/v1/datasets/contracts_qc/schema").json()
    names = [t["name"] for t in schema["tables"]]
    assert names[0] == "data" and "fact_contract" in names
    assert schema["domain"]["pack"] == "government"
    guided = client.get("/api/v1/guided-queries?dataset_id=contracts_qc").json()["items"]
    assert sum(g["source"] == "government" for g in guided) == 12
    kpis = client.get("/api/v1/kpis/contracts_qc").json()["items"]
    assert any(k["kpi_id"] == "total_spend" for k in kpis)


# ------------------------------------------------------------------------------ domain packs


def test_german_credit_suggests_banking_with_roles_and_curated_questions() -> None:
    ds = uploaded("german_credit.csv")
    domain = client.get(f"/api/v1/datasets/{ds}/domain").json()
    assert domain["pack"] == "banking" and domain["suggestions"][0]["pack"] == "banking"
    roles = domain["roles"]
    assert roles["default_flag"]["column"] == "credit_risk"
    # credit_risk is coded 1 = good, 0 = bad: the minority value (bad) is the positive one.
    assert roles["default_flag"]["positive"] == "False"
    assert roles["loan_amount"]["column"] == "amount"
    assert {"age", "duration", "product"} <= set(roles)
    assert all(0 < r["confidence"] <= 0.95 for r in roles.values())
    banking = next(p for p in domain["packs"] if p["id"] == "banking")
    assert any(r["sensitive"] for r in banking["roles"])

    guided = client.get(f"/api/v1/guided-queries?dataset_id={ds}").json()["items"]
    curated = [g for g in guided if g["source"] == "banking"]
    assert {"banking.default_rate_by_product", "banking.default_rate_by_amount_band"} <= {
        g["query_id"] for g in curated
    }
    assert guided[0]["source"] == "banking"  # the pack's questions come first
    kpis = {k["kpi_id"]: k for k in client.get(f"/api/v1/kpis/{ds}").json()["items"]}
    assert kpis["banking.default_rate"]["value"] == pytest.approx(0.3)  # 300 bad of 1,000


def test_user_can_switch_domain_goal_and_roles() -> None:
    ds = uploaded("bank_marketing.csv")
    r = client.put(
        f"/api/v1/datasets/{ds}/domain",
        json={
            "pack": "banking",
            "goal": "portfolio",
            "roles": {
                "default_flag": {"column": "y", "positive": "true"},
                "age": {"column": "age"},
            },
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack"] == "banking" and body["goal"] == "portfolio" and body["confirmed"]
    assert body["job"] is None  # no star schema change: applied at once
    assert set(body["roles"]) == {"default_flag", "age"}
    guided = client.get(f"/api/v1/guided-queries?dataset_id={ds}").json()["items"]
    assert "banking.default_rate_by_age_band" in {g["query_id"] for g in guided}
    kpis = {k["kpi_id"]: k for k in client.get(f"/api/v1/kpis/{ds}").json()["items"]}
    assert 0.05 < kpis["banking.default_rate"]["value"] < 0.2  # y = yes for ~11 %
    # Unmapped roles drop their items, the generic analysis stays.
    assert "banking.avg_loan" not in kpis and "generic.rows" in kpis

    back = client.put(f"/api/v1/datasets/{ds}/domain", json={"pack": "general"}).json()
    assert back["pack"] == "general" and back["roles"] == {}


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({"pack": "astrology"}, 422, "domain.unknown_pack"),
        ({"pack": "banking", "goal": "nope"}, 422, "domain.unknown_goal"),
        ({"pack": "banking", "roles": {"nope": {"column": "age"}}}, 422, "domain.unknown_role"),
        ({"pack": "banking", "roles": {"age": {"column": "nope"}}}, 422, "domain.unknown_column"),
        (
            {"pack": "banking", "roles": {"age": {"column": "age"}, "income": {"column": "age"}}},
            422,
            "domain.column_reused",
        ),
        ({"pack": "government"}, 409, "domain.not_applicable"),
    ],
)
def test_domain_choice_is_validated(body: dict, status: int, code: str) -> None:
    ds = uploaded("bank_marketing.csv")
    r = client.put(f"/api/v1/datasets/{ds}/domain", json=body)
    assert r.status_code == status and r.json()["code"] == code, r.text


def test_sample_datasets_keep_their_domain() -> None:
    r = client.put("/api/v1/datasets/contracts_qc/domain", json={"pack": "general"})
    assert r.status_code == 409 and r.json()["code"] == "domain.seed_fixed"
