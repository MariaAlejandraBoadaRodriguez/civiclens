"""/api/v1/models — red flags and spend forecast (slice 5d). Runs are asynchronous jobs; the
latest result per dataset and model is stored and returned with a localized model card."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_translator
from app.api.problems import ProblemError
from app.api.v1.sql import ready_dataset
from app.db.models import Job, JobStatus, JobType
from app.db.session import get_session
from app.i18n.loader import Translator
from app.services import ml as svc

router = APIRouter(prefix="/api/v1/models", tags=["models"])
SessionDep = Annotated[Session, Depends(get_session)]
TDep = Annotated[Translator, Depends(get_translator)]
LATER = ("classifier", "segments")


class RunRequest(BaseModel):
    dataset_id: str = Field(description="Dataset id (UUID) or seed slug")
    params: dict[str, Any] = Field(default_factory=dict)


class ReviewRequest(BaseModel):
    dataset_id: str
    contract_id: str = Field(min_length=1, max_length=200)
    reviewed: bool = True


def _model(model_type: str) -> str:
    if model_type in svc.MODELS:
        return model_type
    if model_type in LATER:
        raise ProblemError(501, "model.not_available", model_type=model_type)
    raise ProblemError(404, "model.not_available", model_type=model_type)


@router.post("/{model_type}/run", status_code=202)
def run_model(
    model_type: str, body: RunRequest, background: BackgroundTasks, session: SessionDep
) -> JSONResponse:
    model = _model(model_type)
    ds = ready_dataset(session, body.dataset_id)
    params = {k: v for k, v in body.params.items() if k == "entity_id" and isinstance(v, str)}
    job = Job(
        type=JobType.MODEL_RUN,
        status=JobStatus.QUEUED,
        dataset_id=ds.id,
        input_json={"model_type": model, "params": params},
    )
    session.add(job)
    session.commit()
    background.add_task(svc.run_model_job, job.id)
    return JSONResponse(
        {"id": str(job.id), "status": job.status.value},
        status_code=202,
        headers={"Location": f"/api/v1/jobs/{job.id}"},
    )


@router.get("/{model_type}/latest")
def latest(model_type: str, dataset_id: str, session: SessionDep, t: TDep) -> dict[str, Any]:
    """Latest stored result with its model card in the UI language."""
    model = _model(model_type)
    ds = ready_dataset(session, dataset_id)
    result = svc.load_result(ds, model)
    if result is None or "model_type" not in result:
        raise ProblemError(404, "model.not_run", model_type=model)
    return svc.localize(result, t)


@router.post("/red_flags/reviews")
def review(body: ReviewRequest, session: SessionDep) -> dict[str, Any]:
    """Human-in-the-loop: mark a flagged contract as reviewed (or undo it)."""
    ds = ready_dataset(session, body.dataset_id)
    return {
        "dataset_id": str(ds.id),
        "reviewed": svc.set_reviewed(ds, body.contract_id, body.reviewed),
    }
