"""Exact Shapley values (SHAP, interventional) for models with a handful of features.

With ≤ 10 features every coalition can be enumerated (2^M model evaluations per background
row), so the values are exact instead of sampled — and need no extra dependency. The value of
a coalition S for row x is the mean model output over a background sample where the features
in S take x's values (Lundberg & Lee 2017, "interventional" / KernelSHAP target).
Local accuracy holds by construction: base + Σ contributions = f(x).
"""

from __future__ import annotations

from collections.abc import Callable
from itertools import combinations
from math import factorial

import numpy as np

MAX_FEATURES = 10


def shapley_values(
    predict: Callable[[np.ndarray], np.ndarray], x: np.ndarray, background: np.ndarray
) -> tuple[np.ndarray, float]:
    """Return (contributions with shape (n_rows, M), base value) for the rows of ``x``."""
    n_rows, m = x.shape
    if m > MAX_FEATURES:
        raise ValueError(f"exact Shapley values need at most {MAX_FEATURES} features")
    coalitions = [c for size in range(m + 1) for c in combinations(range(m), size)]
    index = {c: i for i, c in enumerate(coalitions)}
    b = len(background)

    # One batch: every coalition × every background row × every explained row.
    batch = np.repeat(background[None, None, :, :], n_rows, axis=0)
    batch = np.repeat(batch, len(coalitions), axis=1)  # (n_rows, C, b, m)
    for ci, coalition in enumerate(coalitions):
        for feature in coalition:
            batch[:, ci, :, feature] = x[:, feature][:, None]
    values = predict(batch.reshape(-1, m)).reshape(n_rows, len(coalitions), b).mean(axis=2)

    weights = {s: factorial(s) * factorial(m - s - 1) / factorial(m) for s in range(m)}
    contrib = np.zeros((n_rows, m))
    for coalition in coalitions:
        for feature in range(m):
            if feature in coalition:
                continue
            with_f = index[tuple(sorted((*coalition, feature)))]
            contrib[:, feature] += weights[len(coalition)] * (
                values[:, with_f] - values[:, index[coalition]]
            )
    return contrib, float(values[0, index[()]])
