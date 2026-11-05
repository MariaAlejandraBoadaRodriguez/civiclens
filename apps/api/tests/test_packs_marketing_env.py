"""Marketing and Environmental packs (PR 6): one fixture each, detection, curated questions,
KPIs, the {limit} template and the pack's ML target — declarative, no engine change."""

from __future__ import annotations

from functools import cache
from pathlib import Path

from fastapi.testclient import TestClient

from app.core import packs
from app.core.analysis.table import build_table
from app.main import app

client = TestClient(app)
FIXTURES = Path(__file__).resolve().parents[3] / "data" / "fixtures"


@cache
def uploaded(name: str) -> str:
    body = (FIXTURES / name).read_bytes()
    r = client.post("/api/v1/datasets", files={"file": (name, body, "application/octet-stream")})
    assert r.status_code == 202, r.text
    assert client.get(r.headers["location"]).json()["status"] == "succeeded"
    return r.json()["dataset"]["id"]


def test_bank_marketing_is_marketing_with_its_roles_questions_and_kpis() -> None:
    ds = uploaded("bank_marketing.csv")
    d = client.get(f"/api/v1/datasets/{ds}/domain").json()
    assert d["pack"] == "marketing" and d["goal"] == "conversion"
    roles = {r: e["column"] for r, e in d["roles"].items()}
    assert roles["converted"] == "y" and roles["channel"] == "contact"
    assert roles["contacts"] == "campaign" and roles["previous_outcome"] == "poutcome"
    guided = client.get(
        f"/api/v1/guided-queries?dataset_id={ds}", headers={"Accept-Language": "es"}
    ).json()["items"]
    curated = [g for g in guided if g["source"] == "marketing"]
    assert curated[0]["query_id"] == "marketing.conversion_by_channel"
    assert curated[0]["title"] == "Conversión por contact"
    kpis = {k["kpi_id"]: k for k in client.get(f"/api/v1/kpis/{ds}").json()["items"]}
    assert 0.1 < kpis["marketing.conversion_rate"]["value"] < 0.13  # y = yes for ~11 %
    assert kpis["marketing.contacts_per_conversion"]["value"] > 10


def test_marketing_model_predicts_conversion_and_flags_duration() -> None:
    ds = uploaded("bank_marketing.csv")
    r = client.post("/api/v1/models/target_model/run", json={"dataset_id": ds})
    assert client.get(r.headers["location"]).json()["status"] == "succeeded"
    result = client.get(f"/api/v1/models/target_model/latest?dataset_id={ds}").json()
    assert result["target"] == "y" and result["positive"] == "True"
    assert "duration" in [lk["feature"] for lk in result["leakage"]]
    assert {"age", "marital"} <= set(result["excluded_sensitive"])


def test_air_quality_is_environmental_with_limit_compliance() -> None:
    ds = uploaded("air_quality_bucaramanga.csv")
    d = client.get(f"/api/v1/datasets/{ds}/domain").json()
    assert d["pack"] == "environmental" and d["goal"] == "compliance"
    roles = {r: e["column"] for r, e in d["roles"].items()}
    assert roles["value"] == "med_concentracion_estandar" and roles["pollutant"] == "msfl_code"
    assert roles["date"] == "med_fecha_inicio" and "station" in roles
    guided = client.get(f"/api/v1/guided-queries?dataset_id={ds}").json()["items"]
    by_id = {g["query_id"]: g for g in guided}
    assert "environmental.exceedances_by_station" in by_id
    sql = by_id["environmental.exceedances_by_station"]["sql"]
    assert "WHEN 'PM10' THEN 75.0" in sql  # Resolution 2254/2017, 24 h
    kpis = {k["kpi_id"]: k for k in client.get(f"/api/v1/kpis/{ds}").json()["items"]}
    assert 0 <= kpis["environmental.exceedance_share"]["value"] <= 1
    assert kpis["environmental.stations"]["value"] == 2
    overview = client.get(f"/api/v1/datasets/{ds}/overview").json()
    assert overview["kpis"][0]["kpi_id"] == "environmental.exceedance_share"


def test_a_mapped_limit_column_wins_over_the_pack_limits() -> None:
    import pandas as pd

    frame = pd.DataFrame(
        {"station": ["a", "b"] * 10, "value": [10.0, 90.0] * 10, "limit": [50.0] * 20}
    )
    _, metas = build_table(frame)
    by = {m.name: m for m in metas}
    pack = packs.packs()["environmental"]
    roles = {"value": {"column": "value"}, "limit": {"column": "limit"}}
    assert packs.render("{value} > {limit}", roles, by, pack) == '"value" > "limit"'
    no_limit = {"value": {"column": "value"}}
    assert packs.render("{value} > {limit}", no_limit, by, pack) == '"value" > 75.0'


def test_sales_and_elections_stay_general() -> None:
    for name in ("sales_adventureworks.xlsx", "us_presidential_results.csv"):
        d = client.get(f"/api/v1/datasets/{uploaded(name)}/domain").json()
        assert d["pack"] == "general", name
