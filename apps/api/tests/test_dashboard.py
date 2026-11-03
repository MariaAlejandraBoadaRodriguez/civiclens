"""Executive dashboard (spec M5): exact combined KPIs, filters, windows, comparison in CAD."""

from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.sql import engine
from app.db.session import SessionLocal
from app.main import app
from app.services import dashboard
from app.services import datasets as datasets_svc
from app.services import sql as sql_svc

client = TestClient(app)
SEEDS = ("secop_co", "contracts_ca", "contracts_qc")
ALL = "&".join(f"dataset_id={s}" for s in SEEDS)


def _get(query: str, lang: str = "en") -> dict[str, Any]:
    r = client.get(f"/api/v1/dashboard?{query}", headers={"Accept-Language": lang})
    assert r.status_code == 200, r.text
    return r.json()


def _kpis(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {k["kpi_id"]: k for k in body["kpis"]}


def _sql(slug: str, query: str) -> Any:
    with SessionLocal() as session:
        ds = datasets_svc.resolve(session, slug)
        return engine.run(sql_svc.ensure_star(ds), query).rows[0][0]


def test_one_dataset_matches_its_star_schema_kpis() -> None:
    body = _get("dataset_id=contracts_ca")
    k = _kpis(body)
    assert [x["kpi_id"] for x in body["kpis"]] == [
        "total_spend",
        "contract_count",
        "avg_value",
        "direct_award_share",
        "hhi",
        "quality_score",
    ]
    assert k["total_spend"]["value"] == pytest.approx(
        _sql("contracts_ca", "SELECT SUM(amount_cad) FROM fact_contract"), rel=1e-9
    )
    assert k["contract_count"]["value"] == _sql(
        "contracts_ca", "SELECT COUNT(*) FROM fact_contract"
    )
    assert k["avg_value"]["median"] == pytest.approx(
        _sql("contracts_ca", "SELECT MEDIAN(amount_cad) FROM fact_contract"), abs=0.01
    )
    assert k["total_spend"]["currency"] == "CAD" and k["total_spend"]["change"] is None  # "all"
    assert k["hhi"]["level"] in ("unconcentrated", "moderate", "high")


def test_three_jurisdictions_combine_exactly_in_cad() -> None:
    body = _get(ALL)
    k = _kpis(body)
    total = sum(_sql(s, "SELECT COALESCE(SUM(amount_cad), 0) FROM fact_contract") for s in SEEDS)
    assert k["total_spend"]["value"] == pytest.approx(total, rel=1e-9)
    assert [b["slug"] for b in body["by_jurisdiction"]] == list(SEEDS)
    assert sum(b["spend"] for b in body["by_jurisdiction"]) == pytest.approx(total, rel=1e-6)
    assert max(b["share_of_max"] for b in body["by_jurisdiction"]) == 1.0
    assert {b["jurisdiction"] for b in body["by_jurisdiction"]} == {"CO", "CA", "QC"}
    # COP → CAD is stated in the data notes (amounts are never shown in mixed currencies).
    assert any("COP" in n and "CAD" in n for n in body["notes"])


def test_last_12_months_has_a_window_and_a_comparison() -> None:
    body = _get("dataset_id=contracts_ca&period=12m")
    window = body["by_jurisdiction"][0]["window"]
    start, end = (
        date.fromisoformat(window["start"] + "-01"),
        date.fromisoformat(window["end"] + "-01"),
    )
    assert (end.year * 12 + end.month) - (start.year * 12 + start.month) == 11
    assert len(body["monthly"]) <= 12 and all(
        window["start"] <= m["month"] <= window["end"] for m in body["monthly"]
    )
    k = _kpis(body)
    in_window = _sql(
        "contracts_ca",
        "SELECT SUM(f.amount_cad) FROM fact_contract f JOIN dim_date d USING (date_id) "
        f"WHERE d.month_start >= DATE '{start}' AND d.month_start <= DATE '{end}'",
    )
    assert k["total_spend"]["value"] == pytest.approx(in_window, rel=1e-9)
    assert (
        k["total_spend"]["change"] is not None
        and k["direct_award_share"]["change_points"] is not None
    )


def test_last_fiscal_year_uses_the_jurisdictions_calendar() -> None:
    body = _get("dataset_id=contracts_ca&period=fy")
    window = body["by_jurisdiction"][0]["window"]
    assert window["fiscal_year"] and window["start"].endswith("-04")  # Canada: April–March


def test_category_filter_narrows_every_figure() -> None:
    every = _kpis(_get("dataset_id=contracts_ca"))
    services = _kpis(_get("dataset_id=contracts_ca&category=services"))
    expected = _sql(
        "contracts_ca", "SELECT COUNT(*) FROM fact_contract WHERE category_id = 'services'"
    )
    assert services["contract_count"]["value"] == expected < every["contract_count"]["value"]


def test_same_request_in_en_and_es_has_identical_machine_fields() -> None:
    en, es = _get(ALL + "&period=12m", "en"), _get(ALL + "&period=12m", "es")
    localized = {"name", "definition", "level_label", "label", "finding", "notes"}

    def machine(v: Any) -> Any:
        if isinstance(v, dict):
            return {k: machine(x) for k, x in v.items() if k not in localized}
        if isinstance(v, list):
            return [machine(x) for x in v]
        return v

    assert machine(en) == machine(es)
    assert en["finding"] != es["finding"] and en["notes"] != es["notes"]
    assert [b["slug"] for b in en["by_jurisdiction"]] == list(SEEDS)


def test_errors_are_problems() -> None:
    assert client.get("/api/v1/dashboard").status_code == 422  # at least one dataset
    r = client.get("/api/v1/dashboard?dataset_id=nope", headers={"Accept-Language": "es"})
    assert r.status_code == 404 and r.json()["code"] == "dataset.not_found"
    too_many = "&".join(f"dataset_id={s}" for s in [*SEEDS, *SEEDS])
    assert client.get(f"/api/v1/dashboard?{too_many}").status_code == 422
    assert client.get("/api/v1/dashboard?dataset_id=secop_co&period=decade").status_code == 422


@pytest.mark.parametrize(
    ("value", "level"), [(0.05, "unconcentrated"), (0.12, "moderate"), (0.4, "high"), (None, None)]
)
def test_hhi_levels(value: float | None, level: str | None) -> None:
    assert dashboard._hhi_level(value) == level


@pytest.mark.parametrize("fmt", ["csv", "parquet"])
def test_star_schema_export_for_bi_tools(fmt: str) -> None:
    import io
    import zipfile

    import pyarrow.csv as pa_csv
    import pyarrow.parquet as pq

    r = client.get(f"/api/v1/datasets/contracts_qc/export?format={fmt}")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert f"civiclens-star-contracts_qc-{fmt}.zip" in r.headers["content-disposition"]
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(zf.namelist())
    assert {f"fact_contract.{fmt}", f"dim_supplier.{fmt}", "README.txt"} <= names
    raw = io.BytesIO(zf.read(f"fact_contract.{fmt}"))
    table = pa_csv.read_csv(raw) if fmt == "csv" else pq.read_table(raw)
    assert table.num_rows == _sql("contracts_qc", "SELECT COUNT(*) FROM fact_contract")
    assert "amount_cad" in table.column_names
    assert client.get("/api/v1/datasets/contracts_qc/export?format=xlsx").status_code == 422
