"""ML Lab orchestration: read contracts from the star schema, run models as jobs, store and
localize the latest result per dataset and model."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

import pandas as pd

from app.core import memory
from app.core.ml import forecast, red_flags
from app.core.sql import engine
from app.db.models import Dataset, Job, JobStatus
from app.db.session import SessionLocal
from app.i18n.loader import Translator
from app.services import sql as sql_svc
from app.services import storage
from app.services.cleaning import context

log = logging.getLogger(__name__)
MODELS = ("red_flags", "forecast")

CONTRACTS_SQL = """
SELECT f.contract_id, f.entity_id, e.entity_name, f.supplier_id, s.supplier_name,
       d.date, d.fiscal_year, d.days_to_fy_end, d.month_start,
       f.amount_cad, f.award_type, f.n_bidders, s.first_seen
FROM fact_contract f
LEFT JOIN dim_entity e USING (entity_id)
LEFT JOIN dim_supplier s USING (supplier_id)
LEFT JOIN dim_date d USING (date_id)
WHERE f.amount_cad IS NOT NULL
"""


def contracts_frame(path: Path) -> pd.DataFrame:
    con = engine.connect(path)
    try:
        return con.execute(CONTRACTS_SQL).df()
    finally:
        con.close()


def result_path(ds: Dataset, model: str) -> Path:
    folder = storage.dataset_dir(ds.id) / "models"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{model}.json"


def run_model(ds: Dataset, model: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    star = sql_svc.ensure_star(ds)
    frame = contracts_frame(star)
    jurisdiction = sql_svc.jurisdiction(ds)
    if model == "red_flags":
        result = red_flags.run(frame, red_flags.RedFlagParams(jurisdiction), context().fx)
    else:
        result = forecast.run(frame, entity_id=(params or {}).get("entity_id"))
    result["origin"] = sql_svc.star_origin(ds)
    result["model_type"] = model
    reviewed = (load_result(ds, model) or {}).get("reviewed", [])
    result["reviewed"] = reviewed
    storage.write_json(result, result_path(ds, model))
    return result


def load_result(ds: Dataset, model: str) -> dict[str, Any] | None:
    return storage.read_json(result_path(ds, model))


def set_reviewed(ds: Dataset, contract_id: str, reviewed: bool) -> list[str]:
    result = load_result(ds, "red_flags") or {"reviewed": []}
    current = set(result.get("reviewed", []))
    (current.add if reviewed else current.discard)(contract_id)
    result["reviewed"] = sorted(current)
    storage.write_json(result, result_path(ds, "red_flags"))
    return result["reviewed"]


def run_model_job(job_id: uuid.UUID) -> None:
    """Background task for POST /api/v1/models/{type}/run."""
    from app.services.datasets import now

    with SessionLocal() as session:
        job = session.get(Job, job_id)
        if job is None or job.dataset_id is None:
            return
        ds = session.get(Dataset, job.dataset_id)
        job.status, job.started_at = JobStatus.RUNNING, now()
        session.commit()
        payload = job.input_json or {}
        try:
            result = run_model(ds, payload["model_type"], payload.get("params"))
            job.result_json = {
                "dataset_id": str(ds.id),
                "model_type": payload["model_type"],
                "summary": summary(result),
            }
            job.status = JobStatus.SUCCEEDED
        except Exception:  # noqa: BLE001 — stable code; details in the server log
            log.exception("model job %s failed", job_id)
            job.status, job.error_code = JobStatus.FAILED, "model.failed"
        job.finished_at = now()
        session.commit()
    memory.release()


def summary(result: dict[str, Any]) -> dict[str, Any]:
    if result["model_type"] == "red_flags":
        return {"contracts": result["contracts"], "flagged": result["flagged"]}
    return {
        "status": result["status"],
        "mape_model": result.get("metrics", {}).get("mape_model"),
        "mape_baseline": result.get("metrics", {}).get("mape_baseline"),
    }


def _pct(value: float | None, lang: str) -> str:
    if value is None:
        return "—"
    text = f"{value * 100:.1f} %"
    return text.replace(".", ",") if lang == "es" else text.replace(" %", "%")


def _amount(value: float, lang: str) -> str:
    text = f"{value:,.0f}"
    return text.replace(",", ".") if lang == "es" else text


def localize(result: dict[str, Any], t: Translator) -> dict[str, Any]:
    """Latest result + its model card in the UI language. Machine fields stay as stored."""
    model = result["model_type"]
    key = f"models.{model}"
    card: dict[str, Any] = {
        "name": t(f"{key}.name"),
        "question": t(f"{key}.question"),
        "method": t(f"{key}.method"),
        "warning": t(f"{key}.warning"),
        "limitations": [t(f"{key}.limitations.l{i}") for i in (1, 2, 3)],
        "features": [
            {"id": f, "label": t(f"{key}.features.{f}")} for f in result.get("features", [])
        ],
    }
    out = {**result, "card": card}
    if model == "red_flags":
        card["method_detail"] = t(
            f"{key}.method_detail", trees=result["n_estimators"], seed=result["seed"]
        )
        card["rules"] = [{"id": r, "label": t(f"{key}.rules.{r}")} for r in result["rules"]]
        thresholds = result["thresholds"]
        card["thresholds"] = t(
            f"{key}.thresholds",
            currency=thresholds["currency"],
            values=" · ".join(_amount(v, t.lang) for v in thresholds["values"]),
        )
        card["flagged_rule"] = t(f"{key}.flagged_rule")
        out["reason_labels"] = {
            r: t(f"{key}.reasons.{r}") for r in (*result["rules"], "unusual_pattern")
        }
    else:
        card["method_detail"] = t(
            f"{key}.method_detail", seed=result["seed"], test=result.get("test_months", 12)
        )
        metrics = result.get("metrics", {})
        if result["status"] == "insufficient_history":
            card["verdict"] = t(
                f"{key}.insufficient", months=result["months"], min=result["min_months"]
            )
        else:
            verdict = "verdict_beats" if metrics.get("beats_baseline") else "verdict_loses"
            card["verdict"] = t(
                f"{key}.{verdict}",
                model=_pct(metrics.get("mape_model"), t.lang),
                baseline=_pct(metrics.get("mape_baseline"), t.lang),
            )
        if result.get("dropped_recent_months"):
            card["dropped"] = t(f"{key}.dropped", n=result["dropped_recent_months"])
    return out
