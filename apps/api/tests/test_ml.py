"""ML Lab (slice 5d): rules, Isolation Forest ranking, SHAP, forecast vs baseline, API."""

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.core.cleaning.ops import FxTable
from app.core.ml import forecast, red_flags
from app.core.ml.shapley import shapley_values
from app.main import app
from app.services.cleaning import context

client = TestClient(app)


def _contract(i: int, **kw) -> dict:
    row = {
        "contract_id": f"C{i:04d}",
        "entity_id": f"E{i % 7}",
        "entity_name": f"Entity {i % 7}",
        "supplier_id": f"S{i % 40}",
        "supplier_name": f"Supplier {i % 40}",
        "date": pd.Timestamp("2022-01-01") + pd.Timedelta(days=(i * 13) % 900),
        "fiscal_year": 2022,
        "days_to_fy_end": 200,
        "month_start": None,
        "amount_cad": 5_000.0 + (i * 7919) % 15_000,
        "award_type": "open",
        "n_bidders": 3 + i % 4,
        "first_seen": pd.Timestamp("2022-01-01"),
    }
    row.update(kw)
    return row


@pytest.fixture(scope="module")
def synthetic() -> pd.DataFrame:
    rows = [_contract(i) for i in range(400)]
    base = pd.Timestamp("2024-03-01")
    rows += [  # split: three contracts of 15 k within 5 days, threshold 40 k (CA)
        _contract(
            900 + k,
            entity_id="EX",
            supplier_id="SX",
            amount_cad=15_000.0,
            date=base + pd.Timedelta(days=2 * k),
        )
        for k in range(3)
    ]
    rows.append(_contract(910, amount_cad=24_500.0))  # just under 25 k
    rows.append(_contract(911, n_bidders=1, award_type="open"))
    rows.append(_contract(912, n_bidders=1, award_type="direct"))  # direct: not the rule
    rows.append(
        _contract(
            913,
            amount_cad=900_000.0,
            supplier_id="SNEW",
            date=pd.Timestamp("2024-06-01"),
            first_seen=pd.Timestamp("2024-05-20"),
        )
    )
    return pd.DataFrame(rows)


def test_rules_fire_on_their_pattern(synthetic: pd.DataFrame) -> None:
    f = red_flags.build_features(synthetic, "CA", context().fx)
    rules = red_flags.apply_rules(f).assign(contract_id=f["contract_id"]).set_index("contract_id")
    assert rules.loc[["C0900", "C0901", "C0902"], "split_contract"].all()
    assert rules.loc["C0910", "under_threshold"]
    assert rules.loc["C0911", "single_bidder"] and not rules.loc["C0912", "single_bidder"]
    assert rules.loc["C0913", "new_large_supplier"]


def test_fy_end_spike_rule() -> None:
    rows = [
        _contract(i, entity_id="E1", fiscal_year=2023, days_to_fy_end=100 + i, amount_cad=10_000.0)
        for i in range(20)
    ]
    rows += [
        _contract(100 + i, entity_id="E1", fiscal_year=2023, days_to_fy_end=5, amount_cad=50_000.0)
        for i in range(3)
    ]
    f = red_flags.build_features(pd.DataFrame(rows), "CA", context().fx)
    fired = f.loc[red_flags.apply_rules(f)["fy_end_spike"].to_numpy(), "contract_id"]
    assert set(fired) == {"C0100", "C0101", "C0102"}


def test_thresholds_convert_local_currency_to_cad() -> None:
    fx = FxTable({"COP": {"2024-01": 0.0003}, "CAD": {"2024-01": 1.0}}, {})
    df = pd.DataFrame({"date": [pd.Timestamp("2024-01-15")]})
    cad = red_flags._thresholds_cad(df, "CO", fx)
    assert cad[0][0] == pytest.approx(142_350_000 * 0.0003)


def test_red_flags_ranking_is_reproducible_and_explained(synthetic: pd.DataFrame) -> None:
    params = red_flags.RedFlagParams("CA")
    a = red_flags.run(synthetic, params, context().fx)
    b = red_flags.run(synthetic.sample(frac=1, random_state=1), params, context().fx)
    assert [i["contract_id"] for i in a["items"]] == [i["contract_id"] for i in b["items"]]
    assert [i["score"] for i in a["items"]] == [i["score"] for i in b["items"]]
    assert a["flagged"] > 0 and a["items"][0]["rank"] == 1
    scores = [i["score"] for i in a["items"]]
    assert scores == sorted(scores, reverse=True)
    top = a["items"][0]
    # Local accuracy: base value + contributions = the item's (normalized) anomaly score.
    total = top["base_value"] + sum(c["value"] for c in top["contributions"])
    assert total == pytest.approx(top["anomaly"], abs=2e-3)
    assert {c["feature"] for c in top["contributions"]} == set(a["features"])


def test_uninformative_features_are_dropped(synthetic: pd.DataFrame) -> None:
    no_bids = synthetic.assign(n_bidders=None)
    result = red_flags.run(no_bids, red_flags.RedFlagParams("CA"), context().fx)
    assert "n_bidders" in result["features_dropped"] and "n_bidders" not in result["features"]


def test_shapley_values_match_a_linear_model() -> None:
    rng = np.random.default_rng(0)
    w = np.array([2.0, -1.0, 0.5])
    background = rng.normal(size=(50, 3))
    x = rng.normal(size=(4, 3))
    contrib, base = shapley_values(lambda m: m @ w, x, background)
    expected = w * (x - background.mean(axis=0))
    assert contrib == pytest.approx(expected)
    assert base == pytest.approx(float((background @ w).mean()))


def _seasonal(months: int, trend: float = 0.01, noise: float = 0.05) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    start = pd.Period("2019-01", freq="M")
    rows = []
    for k in range(months):
        month = start + k
        level = 1_000_000 * (1 + trend * k) * (1.5 if month.month in (3, 12) else 1.0)
        for j in range(4):
            rows.append(
                {
                    "contract_id": f"{k}-{j}",
                    "entity_id": "E1",
                    "date": month.to_timestamp() + pd.Timedelta(days=1 + 7 * j),
                    "amount_cad": level / 4 * (1 + rng.normal(0, noise)),
                }
            )
    rows.append(
        {
            "contract_id": "end",
            "entity_id": "E1",
            "date": (start + months - 1).to_timestamp(how="end").normalize(),
            "amount_cad": 1.0,
        }
    )
    return pd.DataFrame(rows)


def test_forecast_reports_mape_for_model_and_baseline() -> None:
    df = _seasonal(60)
    a, b = forecast.run(df), forecast.run(df)
    assert a["status"] == "ok" and a["test_months"] == 12
    assert a["metrics"] == b["metrics"]  # fixed seed → same metrics
    assert 0 <= a["metrics"]["mape_model"] < 1 and 0 <= a["metrics"]["mape_baseline"] < 1
    assert isinstance(a["metrics"]["beats_baseline"], bool)
    future = [p for p in a["series"] if p["actual"] is None]
    assert len(future) == forecast.HORIZON and all(p["model"] >= 0 for p in future)


def test_forecast_needs_24_months() -> None:
    result = forecast.run(_seasonal(14))
    assert result["status"] == "insufficient_history" and result["months"] < 24


def test_forecast_drops_months_not_yet_reported() -> None:
    df = _seasonal(40)
    last = df["date"].max()
    df = df[df["date"] < last - pd.Timedelta(days=60)]  # two quiet months at the end
    df = pd.concat(
        [
            df,
            pd.DataFrame(
                [{"contract_id": "late", "entity_id": "E1", "date": last, "amount_cad": 10.0}]
            ),
        ]
    )
    series, dropped = forecast.trim(forecast.monthly_series(df))
    assert dropped >= 2 and series.iloc[-1] > 100_000


def test_mape_ignores_zero_months() -> None:
    assert forecast.mape(np.array([0.0, 100.0]), np.array([5.0, 110.0])) == pytest.approx(0.1)


def _run(model: str, dataset: str) -> dict:
    r = client.post(f"/api/v1/models/{model}/run", json={"dataset_id": dataset})
    assert r.status_code == 202, r.text
    job = client.get(r.headers["location"]).json()
    assert job["status"] == "succeeded", job
    return job


def test_models_api_red_flags_en_es() -> None:
    _run("red_flags", "contracts_qc")
    url = "/api/v1/models/red_flags/latest?dataset_id=contracts_qc"
    en = client.get(url, headers={"Accept-Language": "en"}).json()
    es = client.get(url, headers={"Accept-Language": "es"}).json()
    assert [i["contract_id"] for i in en["items"]] == [i["contract_id"] for i in es["items"]]
    assert en["features"] == es["features"] and en["rules"] == es["rules"]
    assert en["card"]["warning"].startswith("Flags are leads for human review")
    assert es["card"]["warning"].startswith("Las alertas son pistas")
    assert en["reason_labels"]["single_bidder"] != es["reason_labels"]["single_bidder"]
    assert len(en["card"]["rules"]) == 5
    contract = en["items"][0]["contract_id"]
    body = {"dataset_id": "contracts_qc", "contract_id": contract}
    assert contract in client.post("/api/v1/models/red_flags/reviews", json=body).json()["reviewed"]
    undo = client.post("/api/v1/models/red_flags/reviews", json={**body, "reviewed": False})
    assert contract not in undo.json()["reviewed"]


def test_models_api_forecast_and_errors() -> None:
    _run("forecast", "contracts_ca")
    url = "/api/v1/models/forecast/latest?dataset_id=contracts_ca"
    en = client.get(url, headers={"Accept-Language": "en"}).json()
    es = client.get(url, headers={"Accept-Language": "es"}).json()
    assert en["status"] == "ok" and en["metrics"] == es["metrics"]
    assert "MAPE" in en["card"]["verdict"] and "MAPE" in es["card"]["verdict"]
    later = client.post("/api/v1/models/classifier/run", json={"dataset_id": "secop_co"})
    assert later.status_code == 501 and later.json()["code"] == "model.not_available"
    assert (
        client.post("/api/v1/models/nope/run", json={"dataset_id": "secop_co"}).status_code == 404
    )
    _run("forecast", "secop_co")
    short = client.get("/api/v1/models/forecast/latest?dataset_id=secop_co").json()
    assert short["status"] == "insufficient_history"
