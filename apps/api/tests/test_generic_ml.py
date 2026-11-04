"""Generic ML on any table (PR 3): target model with baseline, importance, leakage warnings and
a fairness check; anomalies; segments; forecast on any date + quantity. EN/ES model cards."""

from __future__ import annotations

from functools import cache
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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


def run(ds: str, model: str, lang: str = "en", **params: str) -> dict:
    r = client.post(f"/api/v1/models/{model}/run", json={"dataset_id": ds, "params": params})
    assert r.status_code == 202, r.text
    job = client.get(r.headers["location"]).json()
    assert job["status"] == "succeeded", job
    latest = client.get(
        f"/api/v1/models/{model}/latest?dataset_id={ds}", headers={"Accept-Language": lang}
    )
    assert latest.status_code == 200, latest.text
    return latest.json()


def test_banking_default_model_uses_the_pack_target_and_checks_fairness() -> None:
    ds = uploaded("german_credit.csv")
    r = run(ds, "target_model")
    assert r["status"] == "ok" and r["task"] == "binary"
    assert r["target"] == "credit_risk" and r["positive"] == "False"  # 0 = bad credit
    assert r["beats_baseline"] and r["metrics"]["roc_auc"] > 0.6
    assert r["baseline_metrics"]["roc_auc"] == 0.5
    # Sensitive attributes are never inputs, and each gets a fairness check across groups.
    assert {"age", "personal_status_sex", "foreign_worker"} <= set(r["excluded_sensitive"])
    assert not set(r["excluded_sensitive"]) & set(r["features"])
    attrs = {f["attribute"] for f in r["fairness"]}
    assert {"age", "sex"} <= attrs
    for f in r["fairness"]:
        assert f["groups"] and f["verdict"] and f["label"]
        assert all(g["rows"] >= 20 for g in f["groups"])
    assert r["importance"] and r["importance"][0]["label"]
    card = r["card"]
    assert "credit_risk" in card["question"] and card["verdict"].startswith("The model beats")
    assert any("Sensitive attributes" in n for n in card["notes"])


def test_bank_marketing_warns_that_duration_leaks_in_both_languages() -> None:
    ds = uploaded("bank_marketing.csv")
    en = run(ds, "target_model")
    assert en["target"] == "y" and en["positive"] == "True"
    assert [lk["feature"] for lk in en["leakage"]] == ["duration"]
    assert any("Possible leakage: duration" in n for n in en["card"]["notes"])
    es = client.get(
        f"/api/v1/models/target_model/latest?dataset_id={ds}", headers={"Accept-Language": "es"}
    ).json()
    assert any("Posible fuga de información: duration" in n for n in es["card"]["notes"])
    assert es["metrics"] == en["metrics"]  # machine fields identical in every language


def test_user_picks_a_numeric_target_for_a_regression() -> None:
    ds = uploaded("sales_adventureworks.xlsx")
    r = run(ds, "target_model", target="sales_amount")
    assert r["task"] == "regression" and r["baseline"] == "mean"
    assert {"mae", "rmse", "r2"} <= set(r["metrics"]) and r["fairness"] == []
    assert "Sales Amount" in r["card"]["question"]  # the header as written in the file


def test_unknown_target_is_refused_before_any_job() -> None:
    ds = uploaded("sales_adventureworks.xlsx")
    r = client.post(
        "/api/v1/models/target_model/run",
        json={"dataset_id": ds, "params": {"target": "nope"}},
        headers={"Accept-Language": "es"},
    )
    assert r.status_code == 422 and r.json()["code"] == "model.unknown_target"
    assert "nope" in r.json()["detail"]


def test_table_without_a_flag_explains_how_to_get_a_model() -> None:
    ds = uploaded("budget_colombia_pgn.csv")
    r = run(ds, "target_model", lang="es")
    assert r["status"] == "no_target" and "Elige una columna objetivo" in r["card"]["verdict"]


@pytest.mark.parametrize(
    "name",
    [
        "bank_marketing.csv",
        "german_credit.csv",
        "air_quality_bucaramanga.csv",
        "us_presidential_results.csv",
        "budget_colombia_pgn.csv",
        "sales_adventureworks.xlsx",
        "sp500_companies.json",
    ],
)
def test_anomalies_segments_and_forecast_never_fail(name: str) -> None:
    ds = uploaded(name)
    anomalies = run(ds, "anomalies")
    if anomalies["status"] == "ok":
        assert anomalies["top"] and all(row["why"] for row in anomalies["top"])
    else:  # the S&P list has no quantities: it says so
        assert anomalies["status"] == "no_numbers" and anomalies["card"]["verdict"]
    segments = run(ds, "segments", lang="es")
    assert segments["status"] == "ok" and 2 <= segments["k"] <= 6
    assert all(s["profile"].startswith(f"Segmento {s['segment']}") for s in segments["segments"])
    assert abs(sum(s["share"] for s in segments["segments"]) - 1) < 0.01
    forecast = run(ds, "forecast")
    assert forecast["generic"] and forecast["card"]["verdict"]


def test_forecast_on_sales_dates_is_honest_about_the_baseline() -> None:
    r = run(uploaded("sales_adventureworks.xlsx"), "forecast")
    assert r["status"] == "ok" and r["date_column"] == "Order Date"
    assert r["metric_column"] == "Sales Amount" and r["currency"] is None
    assert {"mape_model", "mape_baseline"} <= set(r["metrics"])
    assert "Sales Amount" in r["card"]["method_detail"]


def test_red_flags_stay_procurement_only_and_the_seed_forecast_is_unchanged() -> None:
    ds = uploaded("german_credit.csv")
    r = client.post("/api/v1/models/red_flags/run", json={"dataset_id": ds})
    assert r.status_code == 409 and r.json()["code"] == "domain.procurement_only"
    seed = run("contracts_qc", "forecast")
    assert "generic" not in seed and seed["currency"] == "CAD"


def test_results_are_dropped_when_the_data_changes() -> None:
    ds = uploaded("german_credit.csv")
    run(ds, "segments")
    steps = [{"op": "drop_duplicates", "args": {}}]
    r = client.post(
        f"/api/v1/datasets/{ds}/recipes/apply", json={"recipe": {"name": "d", "steps": steps}}
    )
    assert client.get(r.headers["location"]).json()["status"] == "succeeded"
    stale = client.get(f"/api/v1/models/segments/latest?dataset_id={ds}")
    assert stale.status_code == 404 and stale.json()["code"] == "model.not_run"
