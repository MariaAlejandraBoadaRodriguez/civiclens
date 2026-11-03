"""Cleaning recipes: a versioned JSON list of ``{op, args}`` steps (ADR-0006).

``validate_steps`` rejects unknown operations and arguments before anything runs;
``replay`` folds the steps over the staged data and reports what each step changed.
Same staged data + same recipe → same ``output_hash`` (tested).
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.core.cleaning.ops import OPERATIONS, Context, _strings, output_hash

SCHEMA = "civiclens.recipe/v1"


class RecipeError(ValueError):
    code = "recipe.invalid"

    def __init__(self, message: str, step: int | None = None) -> None:
        super().__init__(message)
        self.step = step


def _signature(op: str) -> inspect.Signature:
    return inspect.signature(OPERATIONS[op])


def validate_steps(steps: object) -> list[dict[str, Any]]:
    """Return a normalized copy of ``steps`` or raise ``RecipeError``."""
    if not isinstance(steps, list):
        raise RecipeError("steps must be a list")
    clean = []
    for i, step in enumerate(steps):
        if not isinstance(step, dict) or "op" not in step:
            raise RecipeError("each step needs an 'op'", i)
        op, args = step["op"], step.get("args", {}) or {}
        if op not in OPERATIONS:
            raise RecipeError(f"unknown operation {op!r}", i)
        if not isinstance(args, dict):
            raise RecipeError("'args' must be an object", i)
        params = {n: p for n, p in _signature(op).parameters.items() if n not in ("df", "ctx")}
        unknown = set(args) - set(params)
        if unknown:
            raise RecipeError(f"unknown argument(s) for {op}: {sorted(unknown)}", i)
        missing = [
            n for n, p in params.items() if p.default is inspect.Parameter.empty and n not in args
        ]
        if missing:
            raise RecipeError(f"missing argument(s) for {op}: {missing}", i)
        clean.append({"op": op, "args": dict(args)})
    return clean


def document(name: str, steps: list[dict[str, Any]], version: int = 1) -> dict[str, Any]:
    """The JSON recipe exactly as exported and stored."""
    return {"schema": SCHEMA, "name": name, "version": version, "steps": steps}


@dataclass
class StepStats:
    op: str
    rows_before: int
    rows_after: int
    cells_changed: int


def _norm_cells(series: pd.Series) -> list[str | None]:
    return [None if v is None else str(v) for v in _strings(series)]


def _changed_cells(before: pd.DataFrame, after: pd.DataFrame) -> int:
    """Cells whose value changed (nulls compared as nulls); new columns count fully.
    Row-removing steps report 0 here — their effect is ``rows_before - rows_after``."""
    if len(before) != len(after):
        return 0
    changed = 0
    for col in after.columns:
        if col not in before.columns:
            changed += int(after[col].notna().sum())
        elif before[col] is not after[col]:
            a, b = _norm_cells(before[col]), _norm_cells(after[col])
            changed += sum(1 for x, y in zip(a, b, strict=True) if x != y)
    return changed


def replay(
    df: pd.DataFrame, steps: list[dict[str, Any]], ctx: Context
) -> tuple[pd.DataFrame, list[StepStats], str]:
    """Apply validated ``steps``; return the output, per-step stats and the output hash."""
    stats: list[StepStats] = []
    for i, step in enumerate(validate_steps(steps)):
        try:
            out = OPERATIONS[step["op"]](df, ctx, **step["args"])
        except KeyError as exc:  # a column the recipe expects is not in this file
            raise RecipeError(f"column not found: {exc.args[0]}", i) from exc
        stats.append(StepStats(step["op"], len(df), len(out), _changed_cells(df, out)))
        df = out
    return df, stats, output_hash(df)
