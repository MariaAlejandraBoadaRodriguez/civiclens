"""Dashboard and report for any table (PR 4): KPI tiles, quality, chart sections with written
findings in EN/ES, a chart the user builds, and the HTML/PDF report."""

from __future__ import annotations

from functools import cache
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
FIXTURES = Path(__file__).resolve().parents[3] / "data" / "fixtures"
NAMES = [
    "bank_marketing.csv",
    "german_credit.csv",
    "air_quality_bucaramanga.csv",
    "us_presidential_results.csv",
    "budget_colombia_pgn.csv",
    "sales_adventureworks.xlsx",
    "sp500_companies.json",
]


@cache
def uploaded(name: str) -> str:
    body = (FIXTURES / name).read_bytes()
    r = client.post("/api/v1/datasets", files={"file": (name, body, "application/octet-stream")})
    assert r.status_code == 202, r.text
    assert client.get(r.headers["location"]).json()["status"] == "succeeded"
    return r.json()["dataset"]["id"]


@pytest.mark.parametrize("name", NAMES)
def test_overview_has_meaningful_sections_for_every_fixture(name: str) -> None:
    ds = uploaded(name)
    en = client.get(f"/api/v1/datasets/{ds}/overview").json()
    es = client.get(f"/api/v1/datasets/{ds}/overview", headers={"Accept-Language": "es"}).json()
    assert len(en["kpis"]) >= 5 and all(k["value"] is not None for k in en["kpis"])
    assert len(en["sections"]) >= 2
    for s in en["sections"]:
        assert s["rows"] and s["title"] and s["finding"] and "{" not in s["finding"] + s["title"]
        assert s["unit"] in ("count", "amount", "ratio", "r")
    assert [s["id"] for s in es["sections"]] == [s["id"] for s in en["sections"]]
    values = [[r["value"] for r in s["rows"]] for s in en["sections"]]
    assert [[r["value"] for r in s["rows"]] for s in es["sections"]] == values
    assert es["sections"][0]["finding"] != en["sections"][0]["finding"]
    assert en["dimensions"]


def test_banking_overview_leads_with_pack_kpis_and_target_drivers() -> None:
    ds = uploaded("german_credit.csv")
    o = client.get(f"/api/v1/datasets/{ds}/overview").json()
    assert o["domain"]["pack"] == "banking"
    assert o["kpis"][0]["kpi_id"] == "banking.default_rate"
    drivers = next(s for s in o["sections"] if s["id"] == "drivers")
    assert drivers["unit"] == "ratio" and "credit_risk rate" in drivers["finding"]
    assert "30.0% overall" in drivers["finding"]  # 300 bad loans of 1,000


def test_sales_overview_shows_the_trend_and_a_monthly_custom_chart() -> None:
    ds = uploaded("sales_adventureworks.xlsx")
    o = client.get(f"/api/v1/datasets/{ds}/overview").json()
    trend = next(s for s in o["sections"] if s["id"] == "trend")
    assert trend["chart"] == "line" and len(trend["rows"]) > 24
    r = client.post(
        f"/api/v1/datasets/{ds}/chart",
        json={
            "dimension": "order_date",
            "grain": "year",
            "aggregation": "sum",
            "metric": "sales_amount",
            "filters": [{"column": "country", "op": "eq", "values": ["United States"]}],
            "chart_type": "line",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert [row["label"] for row in body["rows"]] == sorted(row["label"] for row in body["rows"])
    assert all(len(row["label"]) == 4 for row in body["rows"]) and body["chart"] == "line"
    assert "'United States'" in body["sql"] and body["metric"] == "Sales Amount"


@pytest.mark.parametrize(
    ("spec", "code"),
    [
        ({"dimension": "nope"}, "chart.unknown_column"),
        (
            {"dimension": "country", "aggregation": "sum", "metric": "country"},
            "chart.metric_not_numeric",
        ),
        (
            {
                "dimension": "country",
                "filters": [{"column": "unit_price", "op": "gte", "values": ["x"]}],
            },
            "chart.bad_filter",
        ),
    ],
)
def test_custom_chart_is_validated(spec: dict, code: str) -> None:
    ds = uploaded("sales_adventureworks.xlsx")
    r = client.post(f"/api/v1/datasets/{ds}/chart", json=spec, headers={"Accept-Language": "es"})
    assert r.status_code == 422 and r.json()["code"] == code, r.text


def test_custom_chart_cannot_inject_sql() -> None:
    harmless = "O'Brien"  # quotes are escaped, not refused
    ds = uploaded("sales_adventureworks.xlsx")
    evil = "x'); DROP TABLE data; --"
    r = client.post(
        f"/api/v1/datasets/{ds}/chart",
        json={
            "dimension": "country",
            "filters": [{"column": "country", "op": "in", "values": [evil]}],
        },
    )
    # The value stays a quoted literal; the read-only guard still refuses it, and nothing runs.
    assert r.status_code == 400 and r.json()["code"] == "sql.multiple_statements"
    quoted = client.post(
        f"/api/v1/datasets/{ds}/chart",
        json={"dimension": "country", "filters": [{"column": "country", "values": [harmless]}]},
    )
    assert quoted.status_code == 200 and quoted.json()["rows"] == []
    assert client.post(f"/api/v1/datasets/{ds}/chart", json={"dimension": "country"}).json()["rows"]


@pytest.mark.parametrize("lang", ["en", "es"])
def test_report_for_any_table_in_html_and_pdf(lang: str) -> None:
    ds = uploaded("bank_marketing.csv")
    html = client.get(f"/api/v1/reports/{ds}?lang={lang}")
    assert html.status_code == 200 and f'<html lang="{lang}">' in html.text
    assert ("Data report" if lang == "en" else "Reporte de datos") in html.text
    assert "<script" not in html.text
    overview = client.get(f"/api/v1/datasets/{ds}/overview", headers={"Accept-Language": lang})
    assert overview.json()["sections"][0]["finding"] in html.text.replace("&#39;", "'")
    pdf = client.get(f"/api/v1/reports/{ds}?lang={lang}&format=pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_procurement_report_is_unchanged() -> None:
    html = client.get("/api/v1/reports/contracts_qc?lang=en").text
    assert "Monthly spend" in html and "Data report" not in html
