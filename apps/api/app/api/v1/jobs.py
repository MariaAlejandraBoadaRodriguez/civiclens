"""/api/v1/jobs/{job_id} — poll asynchronous work."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_translator
from app.api.problems import ProblemError, problem_body
from app.db.models import Job
from app.db.session import get_session
from app.i18n.loader import Translator

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get("/{job_id}")
def get_job(
    job_id: str,
    session: Annotated[Session, Depends(get_session)],
    t: Annotated[Translator, Depends(get_translator)],
) -> dict:
    try:
        job = session.get(Job, uuid.UUID(job_id))
    except ValueError:
        job = None
    if job is None:
        raise ProblemError(404, "job.not_found", job_id=job_id)
    error = None
    if job.error_code:
        error = problem_body(t, 422, job.error_code, {}, f"/api/v1/jobs/{job_id}")
    return {
        "id": str(job.id),
        "type": job.type.value,
        "status": job.status.value,
        "dataset_id": str(job.dataset_id) if job.dataset_id else None,
        "result": job.result_json,
        "error": error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }
