"""Cleaning Studio orchestration: issues (cached), localization, recipes and replay jobs."""

from __future__ import annotations

import json
import logging
import uuid
from functools import cache
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.cleaning.codegen import pandas_preview, pandas_script, sql_preview, sql_script
from app.core.cleaning.detectors import detect_issues
from app.core.cleaning.ops import Context, FxTable
from app.core.cleaning.recipe import RecipeError, document, replay, validate_steps
from app.core.profile.profiler import profile_frame
from app.core.seed.registry import SEEDS
from app.db.models import AuditLog, Dataset, DatasetStatus, Job, JobStatus, Recipe
from app.db.session import SessionLocal
from app.i18n.loader import Translator
from app.services import storage

log = logging.getLogger(__name__)
JURISDICTION_CURRENCY = {"CO": "COP", "CA": "CAD", "QC": "CAD"}


@cache
def context() -> Context:
    return Context(fx=FxTable.from_csv(settings.fx_path))


def default_currency(ds: Dataset) -> str | None:
    seed = SEEDS.get(ds.slug or "")
    return JURISDICTION_CURRENCY.get(seed.jurisdiction) if seed else None


# --------------------------------------------------------------------------- issues


def build_issues(ds: Dataset) -> list[dict[str, Any]]:
    """Detect issues on the staged layer and cache them next to the profile."""
    profile = storage.read_json(storage.profile_path(ds.id)) or {}
    staged = storage.read_parquet(storage.staged_path(ds.id))
    issues = [i.to_dict() for i in detect_issues(staged, profile, context(), default_currency(ds))]
    storage.write_json(
        {"issues": issues, "columns": list(staged.columns)}, storage.issues_path(ds.id)
    )
    return issues


def load_issues(ds: Dataset) -> dict[str, Any]:
    cached = storage.read_json(storage.issues_path(ds.id))
    if cached is None:
        build_issues(ds)
        cached = storage.read_json(storage.issues_path(ds.id)) or {"issues": [], "columns": []}
    return cached


def _fmt_number(value: float | int, lang: str, decimals: int = 0) -> str:
    text = f"{value:,.{decimals}f}"
    if lang == "es":
        text = text.replace(",", "\0").replace(".", ",").replace("\0", ".")
    return text


def _fmt_param(key: str, value: Any, lang: str, t: Translator) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if key in ("share",):
        return _fmt_number(value * 100, lang, 1) + " %" if lang == "es" else f"{value * 100:.1f}%"
    if key == "confidence":
        return _fmt_number(value, lang, 2)
    if key in ("high", "low"):
        return _fmt_number(value, lang, 0)
    if key == "breakdown":
        parts = [f"{_fmt_number(b['rows'], lang)} {b['currency']}" for b in value]
        return (
            parts[0]
            if len(parts) == 1
            else f"{', '.join(parts[:-1])} {t('common.and')} {parts[-1]}"
        )
    if isinstance(value, int | float):
        return _fmt_number(value, lang)
    return value


def localize_issue(issue: dict[str, Any], index: int, total: int, t: Translator) -> dict[str, Any]:
    kind = issue["issue_type"]
    params = {k: _fmt_param(k, v, t.lang, t) for k, v in issue["params"].items()}
    if issue.get("field"):
        params.setdefault("field", issue["field"])
    base = f"issues.{kind}"
    options = []
    for opt in issue["options"]:
        key = "use" if opt["option_id"].startswith("use_") else opt["option_id"]
        oparams = {**params, **opt.get("params", {})}
        options.append(
            {
                **opt,
                "label": t(f"{base}.options.{key}.label", **oparams),
                "hint": t(f"{base}.options.{key}.hint", **oparams),
            }
        )
    out = {
        **issue,
        "position": index + 1,
        "of": total,
        "title": t(f"{base}.title", **params),
        "what": t(f"{base}.what", **params),
        "why": t(f"{base}.why", **params),
        "learn_more": t(f"{base}.learn_more", **params),
        "category_label": t(f"quality.{issue['category']}"),
        "options": options,
        "kpi_label": t(f"kpis.{issue['kpi_id']}") if issue.get("kpi_id") else None,
    }
    if kind == "mixed_currency":
        out["fx_note"] = t(
            "issues.mixed_currency.fx_note", source=issue["params"].get("fx_source", "")
        )
    return out


def localized_issues(ds: Dataset, t: Translator) -> dict[str, Any]:
    data = load_issues(ds)
    issues = data["issues"]
    return {
        "issues": [localize_issue(i, n, len(issues), t) for n, i in enumerate(issues)],
        "columns": data["columns"],
    }


# --------------------------------------------------------------------------- code


def code_preview(
    steps: list[dict[str, Any]], columns: list[str], name: str = "recipe"
) -> dict[str, str]:
    steps = validate_steps(steps)
    return {
        "pandas": pandas_preview(steps),
        "sql": sql_preview(steps, columns),
        "json": json.dumps(document(name, steps), ensure_ascii=False, indent=2),
    }


def export(recipe: Recipe, fmt: str, columns: list[str]) -> str:
    doc = document(recipe.name, recipe.steps_json, recipe.version)
    if fmt == "pandas":
        return pandas_script(doc)
    if fmt == "sql":
        return sql_script(doc, columns)
    return json.dumps(doc, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- recipes


def save_recipe(
    session: Session, name: str, steps: list[dict[str, Any]], dataset_id: uuid.UUID | None
) -> Recipe:
    steps = validate_steps(steps)
    latest = session.scalar(select(func.max(Recipe.version)).where(Recipe.name == name)) or 0
    recipe = Recipe(name=name, version=latest + 1, dataset_id=dataset_id, steps_json=steps)
    session.add(recipe)
    session.flush()
    session.add(
        AuditLog(
            actor="anonymous",
            action="recipe.saved",
            target=f"recipe:{recipe.id}",
            details_json={"name": name, "version": recipe.version, "steps": len(steps)},
        )
    )
    session.commit()
    return recipe


def run_apply_job(job_id: uuid.UUID) -> None:
    """Background task: replay a recipe on a dataset's staged layer, profile the result."""
    from app.services.datasets import now

    with SessionLocal() as session:
        job = session.get(Job, job_id)
        if job is None or job.dataset_id is None:
            return
        ds = session.get(Dataset, job.dataset_id)
        job.status, job.started_at = JobStatus.RUNNING, now()
        session.commit()
        try:
            steps = (job.input_json or {}).get("steps", [])
            staged = storage.read_parquet(storage.staged_path(ds.id))
            clean, stats, digest = replay(staged, steps, context())
            storage.write_parquet(clean, storage.clean_path(ds.id), as_text=False)
            storage.star_path(ds.id).unlink(missing_ok=True)  # the SQL Lab rebuilds from it
            after = profile_frame(clean)
            storage.write_json(after, storage.clean_profile_path(ds.id))
            before = (storage.read_json(storage.profile_path(ds.id)) or {}).get("quality", {})
            ds.status = DatasetStatus.CLEANED
            ds.profile_json = {**(ds.profile_json or {}), "quality_after": after["quality"]}
            job.result_json = {
                "dataset_id": str(ds.id),
                "recipe_id": (job.input_json or {}).get("recipe_id"),
                "output_hash": digest,
                "rows_before": len(staged),
                "rows_after": len(clean),
                "steps": [s.__dict__ for s in stats],
                "quality_before": before,
                "quality_after": after["quality"],
            }
            job.status = JobStatus.SUCCEEDED
            session.add(
                AuditLog(
                    actor="anonymous",
                    action="recipe.applied",
                    target=f"dataset:{ds.id}",
                    details_json={
                        "output_hash": digest,
                        "rows_after": len(clean),
                        "steps": len(stats),
                    },
                )
            )
        except RecipeError as exc:
            job.status, job.error_code = JobStatus.FAILED, exc.code
            job.result_json = {"step": exc.step, "message": str(exc)}
        except Exception:  # noqa: BLE001 — stable code; details in the server log
            log.exception("apply job %s failed", job_id)
            job.status, job.error_code = JobStatus.FAILED, "recipe.failed"
        job.finished_at = now()
        session.commit()
