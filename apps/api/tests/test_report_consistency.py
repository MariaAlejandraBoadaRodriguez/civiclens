"""Every number the owner reads twice must be the same number (fix-report-consistency).

The report, the KPIs endpoint, the red-flag result and the dashboard are cross-checked after a
recipe is applied, which is when they used to disagree (25,000 vs 24,830 contracts on secop_co).
"""

import csv
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.reports import format as fmt
from app.main import app

client = TestClient(app)
SEEDS = ("secop_co", "contracts_ca", "contracts_qc")
FX_CSV = Path(__file__).resolve().parents[3] / "data" / "fx_rates.csv"


def _apply_recommended(slug: str) -> None:
    issues = client.get(f"/api/v1/datasets/{slug}/issues").json()["issues"]
    steps = [s for i in issues for o in i["options"] if o["recommended"] for s in o["steps"]]
    r = client.post(
        f"/api/v1/datasets/{slug}/recipes/apply",
        json={"recipe": {"name": "consistency", "steps": steps}},
    )
    assert client.get(r.headers["location"]).json()["status"] == "succeeded"


def _run_red_flags(slug: str) -> dict[str, Any]:
    r = client.post("/api/v1/models/red_flags/run", json={"dataset_id": slug})
    assert client.get(r.headers["location"]).json()["status"] == "succeeded"
    return client.get(f"/api/v1/models/red_flags/latest?dataset_id={slug}").json()


def _kpis(slug: str) -> dict[str, Any]:
    items = client.get(f"/api/v1/kpis/{slug}").json()["items"]
    return {k["kpi_id"]: k["value"] for k in items}


@pytest.fixture(scope="module")
def secop_cleaned() -> dict[str, Any]:
    _apply_recommended("secop_co")
    return _run_red_flags("secop_co")


def test_one_row_count_everywhere_after_a_recipe(secop_cleaned: dict[str, Any]) -> None:
    contracts = _kpis("secop_co")["contract_count"]
    flags = secop_cleaned
    assert flags["contracts"] == contracts  # same denominator as the KPI
    assert flags["scored"] + flags["unscored"] == contracts
    dashboard = client.get("/api/v1/dashboard?dataset_id=secop_co").json()
    tiles = {k["kpi_id"]: k["value"] for k in dashboard["kpis"]}
    assert tiles["contract_count"] == contracts
    for lang in ("en", "es"):
        html = client.get(f"/api/v1/reports/secop_co?lang={lang}").text
        count = fmt.number(contracts, lang, 0)
        summary = re.search(r'id="summary".*?</section>', html, re.S).group(0)
        red = re.search(r'id="red-flags".*?</section>', html, re.S).group(0)
        assert count in summary and count in red, (lang, count)


def test_reason_counts_are_over_the_flagged_contracts(secop_cleaned: dict[str, Any]) -> None:
    flags = secop_cleaned
    counts = flags["reason_counts"]
    assert set(counts) == {*flags["rules"], "unusual_pattern"}
    assert all(0 <= n <= flags["flagged"] for n in counts.values())
    # Every flagged contract has at least one reason; one contract can have several.
    assert sum(counts.values()) >= flags["flagged"]
    html = client.get("/api/v1/reports/secop_co?lang=en").text
    red = re.search(r'id="red-flags".*?</section>', html, re.S).group(0)
    top = sorted(((n, r) for r, n in counts.items() if n), key=lambda x: (-x[0], x[1]))[:3]
    for n, _ in top:
        assert f"({fmt.number(n, 'en', 0)})" in red
    assert "one contract can have several" in red


def test_applying_a_recipe_invalidates_stale_model_results() -> None:
    before = _run_red_flags("contracts_qc")
    contract = before["items"][0]["contract_id"]
    body = {"dataset_id": "contracts_qc", "contract_id": contract, "reviewed": True}
    assert client.post("/api/v1/models/red_flags/reviews", json=body).status_code == 200
    _apply_recommended("contracts_qc")
    stale = client.get("/api/v1/models/red_flags/latest?dataset_id=contracts_qc")
    assert stale.status_code == 404  # must be re-run on the new data
    html = client.get("/api/v1/reports/contracts_qc?lang=en").text
    assert "has not been run on this dataset yet" in html
    after = _run_red_flags("contracts_qc")
    assert after["contracts"] == _kpis("contracts_qc")["contract_count"]
    assert contract in after["reviewed"]  # human review marks survive


def test_fx_table_is_dated_monthly_and_cited() -> None:
    rows = list(csv.DictReader(FX_CSV.open(encoding="utf-8")))
    by_month: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in rows:
        by_month[row["month"]][row["currency"]] = row
    for month, cur in by_month.items():
        assert set(cur) == {"CAD", "USD", "COP"}, month
        for row in cur.values():
            src = row["source"].lower()
            assert "approximate" not in src and "replace" not in src, (month, row["source"])
        assert "FRED" in cur["USD"]["source"] or "Bank of Canada" in cur["USD"]["source"]
        assert "TRM" in cur["COP"]["source"]
    usd_2024 = {by_month[m]["USD"]["cad_per_unit"] for m in by_month if m.startswith("2024")}
    assert len(usd_2024) >= 10  # monthly values, not one annual figure repeated
    note = client.get("/api/v1/dashboard?dataset_id=secop_co").json()["notes"]
    assert not any("approximate" in n or "replace with" in n for n in note)


@pytest.mark.parametrize("query", ["period=12m&category=services", "period=fy&category=goods"])
def test_jurisdiction_panel_uses_the_same_filters_as_the_kpis(query: str) -> None:
    every = "&".join(f"dataset_id={s}" for s in SEEDS)
    combined = client.get(f"/api/v1/dashboard?{every}&{query}").json()
    kpis = {k["kpi_id"]: k["value"] for k in combined["kpis"]}
    rows = {b["slug"]: b for b in combined["by_jurisdiction"]}
    assert sum(b["contracts"] for b in rows.values()) == kpis["contract_count"]
    assert sum(b["spend"] for b in rows.values()) == pytest.approx(kpis["total_spend"], rel=1e-9)
    for slug in SEEDS:  # one jurisdiction alone = its row of the comparison
        alone = client.get(f"/api/v1/dashboard?dataset_id={slug}&{query}").json()
        tiles = {k["kpi_id"]: k["value"] for k in alone["kpis"]}
        assert tiles["contract_count"] == rows[slug]["contracts"], slug
