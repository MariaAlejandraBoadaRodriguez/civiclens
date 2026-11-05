"""/api/v1/models — red flags and spend forecast for procurement data (slice 5d); target model,
anomalies, segments and forecast for any dataset (generic core). Runs are asynchronous jobs; the
latest result per dataset and model is stored and returned with a localized model card."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr
from sqlalchemy.orm import Session

from app.api.deps import get_translator
from app.api.problems import ProblemError
from app.api.security import Principal, require_scope
from app.api.v1.sql import procurement_dataset, ready_dataset
from app.core import jobs
from app.db.models import Job, JobStatus, JobType
from app.db.session import get_session
from app.i18n.loader import Translator
from app.services import ml as svc

router = APIRouter(prefix="/api/v1/models", tags=["models"])
SessionDep = Annotated[Session, Depends(get_session)]
TDep = Annotated[Translator, Depends(get_translator)]


class RunParams(BaseModel):
    """Known parameters are typed strictly; unknown ones are accepted and ignored."""

    model_config = ConfigDict(extra="allow")
    entity_id: StrictStr | None = None
    target: StrictStr | None = Field(
        default=None, max_length=200, description="target_model: column of table `data`"
    )
    positive: StrictStr | None = Field(
        default=None, max_length=200, description="target_model: the value that means yes"
    )


class RunRequest(BaseModel):
    dataset_id: str = Field(description="Dataset id (UUID) or seed slug")
    params: RunParams = Field(default_factory=RunParams)


class ReviewRequest(BaseModel):
    dataset_id: str
    contract_id: str = Field(min_length=1, max_length=200)
    reviewed: StrictBool = True


def _dataset(session: Session, ref: str, model: str):
    """Red flags need the procurement star schema; every other model runs on any dataset."""
    if model in svc.PROCUREMENT_ONLY:
        return procurement_dataset(session, ref)
    return ready_dataset(session, ref)


def _headers(ds) -> dict[str, str]:
    from app.services import analysis

    return {c.name: c.source for c in analysis.columns(ds)}


def _model(model_type: str) -> str:
    if model_type in svc.MODELS:
        return model_type
    # Planned models (classifier, segments) do not exist yet: 404, like an unknown model.
    raise ProblemError(404, "model.not_available", model_type=model_type)


@router.post("/{model_type}/run", status_code=202)
def run_model(
    model_type: str,
    body: RunRequest,
    background: BackgroundTasks,
    session: SessionDep,
    caller: Annotated[Principal, Depends(require_scope("models:run"))],
) -> JSONResponse:
    model = _model(model_type)
    ds = _dataset(session, body.dataset_id, model)
    params: dict[str, Any] = {}
    if body.params.entity_id:
        params["entity_id"] = body.params.entity_id
    if model == "target_model" and body.params.target:
        if body.params.target not in _headers(ds):
            raise ProblemError(422, "model.unknown_target", target=body.params.target)
        params["target"] = body.params.target
        if body.params.positive is not None:
            params["positive"] = body.params.positive
    job = Job(
        type=JobType.MODEL_RUN,
        status=JobStatus.QUEUED,
        dataset_id=ds.id,
        api_key_id=caller.key_id,
        input_json={"model_type": model, "params": params},
    )
    session.add(job)
    session.commit()
    background.add_task(jobs.run, jobs.MODEL_RUN, job.id)
    return JSONResponse(
        {"id": str(job.id), "status": job.status.value},
        status_code=202,
        headers={"Location": f"/api/v1/jobs/{job.id}"},
    )


@router.get("/{model_type}/latest")
def latest(model_type: str, dataset_id: str, session: SessionDep, t: TDep) -> dict[str, Any]:
    """Latest stored result with its model card in the UI language."""
    model = _model(model_type)
    ds = _dataset(session, dataset_id, model)
    result = svc.load_result(ds, model)
    if result is None or "model_type" not in result:
        raise ProblemError(404, "model.not_run", model_type=model)
    return svc.localize(result, t, _headers(ds))


@router.post("/red_flags/reviews", dependencies=[Depends(require_scope("models:run"))])
def review(body: ReviewRequest, session: SessionDep) -> dict[str, Any]:
    """Human-in-the-loop: mark a flagged contract as reviewed (or undo it)."""
    ds = procurement_dataset(session, body.dataset_id)
    return {
        "dataset_id": str(ds.id),
        "reviewed": svc.set_reviewed(ds, body.contract_id, body.reviewed),
    }
