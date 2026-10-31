"""Monthly spend forecast with an honest baseline (spec M6.2, US-19).

Baseline: seasonal naive (next month = same month last year). Model: gradient boosting on
lags (1, 2, 3, 12), a 3-month mean and the month of the year, trained on log spend and
forecast recursively. Both are scored with MAPE on the last 12 months (6 when history is
short); the card says plainly when the model does not beat the baseline.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.core.ml import SEED

MIN_MONTHS = 24
SEASON = 12
HORIZON = 6
HISTORY_SHOWN = 36
LAGS = (1, 2, 3, 12)
MAX_MONTHS = 72  # older history describes another procurement regime; keep six years
LAG_SHARE = 0.05  # trailing months below 5 % of the prior-year median = not reported yet


def monthly_series(df: pd.DataFrame, entity_id: str | None = None) -> pd.Series:
    """Total CAD spend per calendar month, gaps filled with 0, partial edge months dropped."""
    data = df if entity_id is None else df[df["entity_id"] == entity_id]
    data = data.dropna(subset=["date"])
    if data.empty:
        return pd.Series(dtype=float)
    dates = pd.to_datetime(data["date"])
    months = dates.dt.to_period("M")
    series = data["amount_cad"].groupby(months).sum().astype(float)
    full = pd.period_range(months.min(), months.max(), freq="M")
    series = series.reindex(full, fill_value=0.0)
    # A month is partial when the data starts after its 3rd day or ends before its last 3 days.
    if dates.max().day < dates.max().days_in_month - 2:
        series = series.iloc[:-1]
    if dates.min().day > 3:
        series = series.iloc[1:]
    return series


def trim(series: pd.Series) -> tuple[pd.Series, int]:
    """Drop trailing months that look not yet reported (publication lag), then keep the
    most recent ``MAX_MONTHS``. Returns (series, trailing months dropped)."""
    dropped = 0
    while len(series) > SEASON:
        reference = series.iloc[-SEASON - 1 : -1].median()
        if reference > 0 and series.iloc[-1] < LAG_SHARE * reference:
            series, dropped = series.iloc[:-1], dropped + 1
        else:
            break
    return series.iloc[-MAX_MONTHS:], dropped


def mape(actual: np.ndarray, predicted: np.ndarray) -> float | None:
    mask = actual > 0
    if not mask.any():
        return None
    return float(np.mean(np.abs(actual[mask] - predicted[mask]) / actual[mask]))


def _row(history: list[float], month: int) -> list[float]:
    logs = np.log1p(np.maximum(history, 0.0))
    return [
        *(logs[-lag] for lag in LAGS),
        float(np.mean(logs[-3:])),
        np.sin(2 * np.pi * month / 12),
        np.cos(2 * np.pi * month / 12),
    ]


def _fit(values: list[float], months: list[int]):
    from sklearn.ensemble import GradientBoostingRegressor  # lazy: ~85 MB, only when used

    x, y = [], []
    for t in range(max(LAGS), len(values)):
        x.append(_row(values[:t], months[t]))
        y.append(np.log1p(max(values[t], 0.0)))
    model = GradientBoostingRegressor(
        n_estimators=300, max_depth=2, learning_rate=0.05, subsample=0.8, random_state=SEED
    )
    return model.fit(np.array(x), np.array(y))


def _recursive(model, history: list[float], months: list[int]) -> list[float]:
    values = list(history)
    out = []
    for month in months:
        pred = float(np.expm1(model.predict(np.array([_row(values, month)]))[0]))
        pred = max(pred, 0.0)
        out.append(pred)
        values.append(pred)
    return out


def _point(period: pd.Period, **values: float | None) -> dict[str, Any]:
    return {
        "month": str(period),
        **{k: None if v is None else round(float(v), 2) for k, v in values.items()},
    }


def run(df: pd.DataFrame, entity_id: str | None = None) -> dict[str, Any]:
    series, lagged = trim(monthly_series(df, entity_id))
    base: dict[str, Any] = {
        "model": "gradient_boosting",
        "baseline": "seasonal_naive",
        "seed": SEED,
        "entity_id": entity_id,
        "currency": "CAD",
        "features": [f"lag_{lag}" for lag in LAGS] + ["mean_3", "month_of_year"],
        "months": len(series),
        "dropped_recent_months": lagged,
        "min_months": MIN_MONTHS,
    }
    if len(series) < MIN_MONTHS:
        return {
            **base,
            "status": "insufficient_history",
            "metrics": {},
            "series": [_point(p, actual=v) for p, v in series.items()],
        }

    test = SEASON if len(series) >= 3 * SEASON else HORIZON
    values = series.to_list()
    months = [p.month for p in series.index]
    train_values, test_values = values[:-test], np.array(values[-test:])

    baseline_pred = np.array(values[-test - SEASON : -SEASON])
    model = _fit(train_values, months[:-test])
    model_pred = np.array(_recursive(model, train_values, months[-test:]))
    mape_model, mape_baseline = mape(test_values, model_pred), mape(test_values, baseline_pred)
    beats = mape_model is not None and mape_baseline is not None and mape_model < mape_baseline

    future_index = pd.period_range(series.index[-1] + 1, periods=HORIZON, freq="M")
    final = _fit(values, months)
    future_model = _recursive(final, values, [p.month for p in future_index])
    future_baseline = [values[-SEASON + h] for h in range(HORIZON)]

    shown = series.iloc[-HISTORY_SHOWN:]
    test_start = len(series) - test
    points = []
    for offset, (period, actual) in enumerate(shown.items()):
        i = len(series) - len(shown) + offset
        in_test = i >= test_start
        points.append(
            _point(
                period,
                actual=actual,
                model=model_pred[i - test_start] if in_test else None,
                baseline=baseline_pred[i - test_start] if in_test else None,
            )
        )
    points += [
        _point(p, actual=None, model=m, baseline=b)
        for p, m, b in zip(future_index, future_model, future_baseline, strict=True)
    ]
    return {
        **base,
        "status": "ok",
        "train_months": len(train_values),
        "test_months": test,
        "test_start": str(series.index[test_start]),
        "metrics": {
            "mape_model": None if mape_model is None else round(mape_model, 4),
            "mape_baseline": None if mape_baseline is None else round(mape_baseline, 4),
            "beats_baseline": bool(beats),
        },
        "series": points,
    }
