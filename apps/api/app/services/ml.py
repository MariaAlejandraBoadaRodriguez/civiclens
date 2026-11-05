"""ML Lab orchestration: run models as jobs, store and localize the latest result per dataset
and model. Procurement data (Government pack) keeps red flags and the spend forecast on the star
schema; every dataset gets the generic models on its table ``data`` (target model, anomalies,
segments, forecast on any date + quantity)."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

import pandas as pd

from app.core import memory
from app.core.ml import forecast, generic, red_flags
from app.core.sql import engine
from app.db.models import Dataset, Job, JobStatus
from app.db.session import SessionLocal
from app.i18n.loader import Translator
from app.services import sql as sql_svc
from app.services import storage
from app.services.cleaning import context

log = logging.getLogger(__name__)
MODELS = ("red_flags", "forecast", "target_model", "anomalies", "segments")
PROCUREMENT_ONLY = ("red_flags",)
GENERIC = ("target_model", "anomalies", "segments")

CONTRACTS_SQL = """
SELECT f.contract_id, f.entity_id, e.entity_name, f.supplier_id, s.supplier_name,
       d.date, d.fiscal_year, d.days_to_fy_end, d.month_start,
       f.amount_cad, f.award_type, f.n_bidders, s.first_seen
FROM fact_contract f
LEFT JOIN dim_entity e USING (entity_id)
LEFT JOIN dim_supplier s USING (supplier_id)
LEFT JOIN dim_date d USING (date_id)
"""  # every contract: red flags count them all and score those with an amount and a date


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


def data_frame(path: Path) -> pd.DataFrame:
    con = engine.connect(path)
    try:
        return con.execute("SELECT * FROM data").df()
    finally:
        con.close()


def default_target(ds: Dataset) -> tuple[str | None, str | None]:
    """The column a target model predicts by default, with its positive value: the domain
    pack's target role (Banking: the default flag) when mapped, else the table's target-like
    flag."""
    from app.core import packs
    from app.core.analysis.questions import pick
    from app.services import analysis

    active = analysis.domain(ds)
    pack = packs.packs()[active["pack"]]
    metas = analysis.columns(ds)
    names = {m.name for m in metas}
    for objective in pack.ml:
        role = objective.get("target_role")
        entry = active["roles"].get(role or "")
        if entry and entry.get("column") in names:
            return entry["column"], entry.get("positive")
    target = pick(metas).target
    return (target.name if target else None), None


def sensitive_roles(ds: Dataset) -> dict[str, str]:
    from app.core import packs
    from app.services import analysis

    active = analysis.domain(ds)
    pack = packs.packs()[active["pack"]]
    out = {}
    for role in pack.roles:
        entry = active["roles"].get(role.id)
        if role.sensitive and entry:
            out[role.id] = entry["column"]
    return out


def run_generic(ds: Dataset, model: str, params: dict[str, Any]) -> dict[str, Any]:
    from app.services import analysis

    path = sql_svc.ensure_star(ds)
    frame = data_frame(path)
    metas = analysis.columns(ds)
    if model == "target_model":
        target, positive = params.get("target"), params.get("positive")
        if not target:
            target, positive = default_target(ds)
        if target is None:
            return {"status": "no_target"}
        if target not in frame.columns:
            raise ValueError(target)
        return generic.target_model(frame, metas, target, positive, sensitive_roles(ds))
    if model == "anomalies":
        return generic.anomalies(frame, metas)
    if model == "segments":
        return generic.segments(frame, metas)
    found = generic.forecast_input(frame, metas)  # forecast on any date + quantity
    if found is None:
        return {"status": "no_date", "generic": True}
    series_frame, date, metric = found
    by_name = {m.name: m for m in metas}
    result = forecast.run(series_frame)
    return {
        **result,
        "generic": True,
        "currency": None,
        "date_column": by_name[date].source,
        "metric_column": by_name[metric].source if metric else None,
    }


def run_model(ds: Dataset, model: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    params = params or {}
    if model in GENERIC or (model == "forecast" and not sql_svc.has_star(ds)):
        result = run_generic(ds, model, params)
        result["origin"] = sql_svc.star_origin(ds)
        result["model_type"] = model
        storage.write_json(result, result_path(ds, model))
        return result
    star = sql_svc.ensure_star(ds)
    frame = contracts_frame(star)
    jurisdiction = sql_svc.jurisdiction(ds)
    if model == "red_flags":
        result = red_flags.run(frame, red_flags.RedFlagParams(jurisdiction), context().fx)
    else:
        frame = frame[frame["amount_cad"].notna()]  # what the forecast always used
        result = forecast.run(frame, entity_id=(params or {}).get("entity_id"))
    result["origin"] = sql_svc.star_origin(ds)
    result["model_type"] = model
    reviewed = (load_result(ds, model) or {}).get("reviewed", [])
    result["reviewed"] = reviewed
    storage.write_json(result, result_path(ds, model))
    return result


def invalidate_results(ds: Dataset) -> None:
    """The star schema changed (a recipe was applied): stored model results describe other data,
    so they are dropped. Only the human review marks are kept."""
    for model in MODELS:
        path = result_path(ds, model)
        old = storage.read_json(path)
        if old is not None:
            storage.write_json({"reviewed": old.get("reviewed", [])}, path)


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
        job.phase, job.progress = "training", 15
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
            job.phase, job.progress = "done", 100
        except Exception:  # noqa: BLE001 — stable code; details in the server log
            log.exception("model job %s failed", job_id)
            job.status, job.error_code = JobStatus.FAILED, "model.failed"
        job.finished_at = now()
        session.commit()
    memory.release()


def summary(result: dict[str, Any]) -> dict[str, Any]:
    if result["model_type"] in GENERIC:
        return {"status": result.get("status"), "beats_baseline": result.get("beats_baseline")}
    if result["model_type"] == "red_flags":
        return {"contracts": result["contracts"], "flagged": result["flagged"]}
    return {
        "status": result.get("status"),
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


def _labels(ds_columns: dict[str, str], names: list[str]) -> list[dict[str, str]]:
    return [{"id": n, "label": ds_columns.get(n, n)} for n in names]


def localize_generic(
    result: dict[str, Any], t: Translator, headers: dict[str, str]
) -> dict[str, Any]:
    """Model card for the generic models. Column names appear as written in the file."""
    model = result["model_type"]
    key = "models.forecast_any" if model == "forecast" else f"models.{model}"
    status = result.get("status", "ok")
    card: dict[str, Any] = {
        "name": t(f"{key}.name"),
        "question": t(f"{key}.question"),
        "method": t(f"{key}.method"),
        "warning": t(f"{key}.warning"),
        "limitations": [t(f"{key}.limitations.l{i}") for i in (1, 2, 3)],
        "features": _labels(headers, result.get("features", [])),
        "notes": [],
    }
    if status != "ok" and model != "forecast":
        card["verdict"] = t(f"models.generic.status.{status}")
    if result.get("sampled"):
        card["notes"].append(
            t("models.generic.sampled", rows=result["rows_used"], total=result["rows"])
        )
    if model == "target_model" and status == "ok":
        target = headers.get(result["target"], result["target"])
        task = result["task"]
        card["question"] = t(f"{key}.questions.{task}", target=target)
        card["method_detail"] = t(
            f"{key}.method_detail",
            seed=result["seed"],
            train=result["train_rows"],
            test=result["test_rows"],
            baseline=t(f"{key}.baselines.{result['baseline']}"),
        )
        m, b = result["metrics"], result["baseline_metrics"]
        main = {"binary": "roc_auc", "multiclass": "accuracy", "regression": "mae"}[task]
        verdict = "verdict_beats" if result["beats_baseline"] else "verdict_loses"
        card["verdict"] = t(
            f"{key}.{verdict}",
            metric=t(f"{key}.metrics.{main}"),
            model=_num(m[main], t.lang),
            baseline=_num(b[main], t.lang),
        )
        if task == "binary":
            card["positive"] = t(f"{key}.positive", target=target, value=result["positive"])
        for leak in result["leakage"]:
            card["notes"].append(
                t(
                    f"{key}.leakage.{leak['reason']}",
                    column=headers.get(leak["feature"], leak["feature"]),
                    strength=_num(leak["strength"], t.lang),
                )
            )
        if result["excluded_sensitive"]:
            card["notes"].append(
                t(
                    f"{key}.sensitive_excluded",
                    columns=", ".join(headers.get(c, c) for c in result["excluded_sensitive"]),
                )
            )
        for f in result["fairness"]:
            f["label"] = t(f"models.generic.sensitive.{f['attribute']}")
            f["verdict"] = t(
                f"{key}.fairness.{'passes' if f['passes'] else 'fails'}",
                column=headers.get(f["column"], f["column"]),
                ratio="—" if f["disparity_ratio"] is None else _num(f["disparity_ratio"], t.lang),
            )
        for row in result["importance"]:
            row["label"] = headers.get(row["feature"], row["feature"])
        card["metric_labels"] = {k: t(f"{key}.metrics.{k}") for k in {**m, **b}}
    if model == "anomalies" and status == "ok":
        card["method_detail"] = t(f"{key}.method_detail", seed=result["seed"])
        card["verdict"] = t(
            f"{key}.verdict", flagged=result["flagged"], share=_pct(result["flagged_share"], t.lang)
        )
        for row in result["top"]:
            row["label"] = headers.get(row["feature"], row["feature"])
            row["why"] = t(
                f"{key}.{'why_high' if row['z'] > 0 else 'why_low'}",
                column=row["label"],
                value=_num(row["value"], t.lang),
                median=_num(row["median"], t.lang),
            )
    if model == "segments" and status == "ok":
        card["method_detail"] = t(
            f"{key}.method_detail",
            seed=result["seed"],
            k=result["k"],
            silhouette=_num(result["silhouette"], t.lang),
        )
        for seg in result["segments"]:
            parts = []
            for tr in seg["traits"]:
                if tr["kind"] == "number":
                    parts.append(
                        t(
                            f"{key}.trait_{tr['direction']}",
                            column=tr["column"],
                            value=_num(tr["median"], t.lang),
                            overall=_num(tr["overall"], t.lang),
                        )
                    )
                else:
                    parts.append(
                        t(
                            f"{key}.trait_category",
                            column=tr["column"],
                            value=tr["value"],
                            share=_pct(tr["share"], t.lang),
                            overall=_pct(tr["overall"], t.lang),
                        )
                    )
            seg["profile"] = t(
                f"{key}.profile",
                n=seg["segment"],
                share=_pct(seg["share"], t.lang),
                traits="; ".join(parts) if parts else t(f"{key}.typical"),
            )
    if model == "forecast":
        card["method_detail"] = t(
            f"{key}.method_detail",
            seed=result.get("seed", 42),
            test=result.get("test_months", 12),
            date=result.get("date_column") or "—",
            metric=result.get("metric_column") or t(f"{key}.rows"),
        )
        metrics = result.get("metrics", {})
        if status == "no_date":
            card["verdict"] = t("models.generic.status.no_date")
        elif status == "insufficient_history":
            card["verdict"] = t(
                "models.forecast.insufficient", months=result["months"], min=result["min_months"]
            )
        else:
            verdict = "verdict_beats" if metrics.get("beats_baseline") else "verdict_loses"
            card["verdict"] = t(
                f"models.forecast.{verdict}",
                model=_pct(metrics.get("mape_model"), t.lang),
                baseline=_pct(metrics.get("mape_baseline"), t.lang),
            )
        card["features"] = [
            {"id": f, "label": t(f"models.forecast.features.{f}")}
            for f in result.get("features", [])
        ]
    return {**result, "card": card}


def _num(value: float | None, lang: str) -> str:
    if value is None:
        return "—"
    text = f"{value:,.3f}".rstrip("0").rstrip(".") if abs(value) < 1000 else f"{value:,.0f}"
    if lang == "es":
        text = text.replace(",", "\u2009").replace(".", ",").replace("\u2009", ".")
    return text


def localize(
    result: dict[str, Any], t: Translator, headers: dict[str, str] | None = None
) -> dict[str, Any]:
    """Latest result + its model card in the UI language. Machine fields stay as stored."""
    model = result["model_type"]
    if model in GENERIC or result.get("generic"):
        return localize_generic(result, t, headers or {})
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
