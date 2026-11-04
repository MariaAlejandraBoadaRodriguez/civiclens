"""Unit tests of app.core.ml.generic on synthetic tables with known answers."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.core.analysis.table import build_table
from app.core.ml import generic


def _table(n: int = 600) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    income = rng.normal(50, 10, n)
    gender = rng.choice(["f", "m"], n)
    y = (income + rng.normal(0, 8, n) > 55).astype(int)
    return pd.DataFrame(
        {
            "income": income.round(1),
            "region": rng.choice(["n", "s", "e"], n),
            "gender": gender,
            "refund_after": y * 100 + rng.integers(0, 3, n),  # known only after the outcome
            "default": y,
        }
    )


def test_leak_is_flagged_and_sensitive_columns_are_not_inputs() -> None:
    typed, metas = build_table(_table())
    r = generic.target_model(typed, metas, "default")
    assert r["status"] == "ok" and r["task"] == "binary" and r["positive"] == "1"
    assert [lk["feature"] for lk in r["leakage"]] == ["refund_after"]
    assert "gender" not in r["features"] and r["excluded_sensitive"] == ["gender"]
    sex = {f["attribute"]: f for f in r["fairness"]}["sex"]
    assert {g["group"] for g in sex["groups"]} == {"f", "m"}
    # The leak makes the model perfect: every group gets the same true/false positive rates.
    assert {(g["true_positive_rate"], g["false_positive_rate"]) for g in sex["groups"]} == {
        (1.0, 0.0)
    }


def test_fairness_fails_when_one_group_is_almost_never_flagged() -> None:
    actual = np.array([1, 0] * 50)
    predicted = np.array([True] * 50 + [False] * 50)
    values = pd.Series(["a"] * 50 + ["b"] * 50)
    f = generic._fairness("sex", "gender", None, values, actual, predicted)
    assert f["disparity_ratio"] == 0 and not f["passes"]


def test_large_tables_are_sampled_and_say_so(monkeypatch) -> None:
    monkeypatch.setattr(generic, "MAX_ROWS", 300)
    typed, metas = build_table(_table(900))
    r = generic.target_model(typed, metas, "default")
    assert r["sampled"] and r["rows"] == 900 and r["rows_used"] < 900


def test_whole_number_labels_have_no_decimals() -> None:
    assert generic.labels(pd.Series([8204.0, 20385.0, None])).tolist()[:2] == ["8204", "20385"]
