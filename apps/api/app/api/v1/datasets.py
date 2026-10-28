"""/api/v1/datasets — list, upload, metadata and profile (slice 5a)."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_translator
from app.api.problems import ProblemError
from app.api.v1.recipes import RecipeInput, validated
from app.config import settings
from app.core.cleaning.ops import OPERATIONS
from app.core.ingest.detect import UnsupportedFormatError, detect_format
from app.core.seed.registry import SEEDS
from app.db.models import Dataset, DatasetSource, DatasetStatus, Job, JobStatus, JobType, Recipe
from app.db.session import get_session
from app.i18n.loader import Translator
from app.services import cleaning
from app.services import datasets as svc

router = APIRouter(prefix="/api/v1/datasets", tags=["datasets"])
SessionDep = Annotated[Session, Depends(get_session)]
TDep = Annotated[Translator, Depends(get_translator)]
CHUNK = 1 << 20


def dataset_out(ds: Dataset, t: TDep) -> dict[str, Any]:
    seed = SEEDS.get(ds.slug or "")
    return {
        "id": str(ds.id),
        "slug": ds.slug,
        "name": t(f"datasets.{ds.slug}.name") if seed else ds.name,
        "description": t(f"datasets.{ds.slug}.description") if seed else None,
        "source": ds.source.value,
        "format": ds.format.value,
        "data_lang": ds.data_lang.value,
        "status": ds.status.value,
        "rows": ds.rows,
        "columns": ds.columns,
        "quality_score": ds.quality_score,
        "license": seed.license if seed else None,
        "source_url": seed.source_url if seed else None,
        "jurisdiction": seed.jurisdiction if seed else None,
        "created_at": ds.created_at.isoformat() if ds.created_at else None,
        "expires_at": ds.expires_at.isoformat() if ds.expires_at else None,
    }


def job_ref(job: Job) -> dict[str, str]:
    return {"id": str(job.id), "status": job.status.value}


@router.get("")
def list_datasets(session: SessionDep, t: TDep, source: str | None = None) -> dict:
    items = [dataset_out(d, t) for d in svc.list_datasets(session)]
    if source:
        items = [i for i in items if i["source"] == source]
    return {"items": items}


@router.post("", status_code=202)
async def upload_dataset(
    request: Request,
    background: BackgroundTasks,
    session: SessionDep,
    t: TDep,
    file: Annotated[UploadFile, File()],
    name: Annotated[str | None, Form(max_length=255)] = None,
) -> JSONResponse:
    limit = settings.upload_max_mb * 1024 * 1024
    chunks, size = [], 0
    while chunk := await file.read(CHUNK):
        size += len(chunk)
        if size > limit:
            raise ProblemError(413, "ingest.too_large", limit_mb=settings.upload_max_mb)
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data.strip():
        raise ProblemError(400, "ingest.empty_file")
    filename = file.filename or "upload"
    try:
        fmt = detect_format(filename, data[:8192])
    except UnsupportedFormatError as exc:
        raise ProblemError(415, "ingest.unsupported_format") from exc
    svc.purge_expired(session)
    ds, job = svc.create_upload(session, filename, data, fmt.value, name)
    background.add_task(svc.run_ingest_job, job.id)
    return JSONResponse(
        {"dataset": dataset_out(ds, t), "job": job_ref(job)},
        status_code=202,
        headers={"Location": f"/api/v1/jobs/{job.id}"},
    )


def _get(session: Session, dataset_id: str) -> Dataset:
    ds = svc.resolve(session, dataset_id)
    if ds is None:
        raise ProblemError(404, "dataset.not_found", dataset_id=dataset_id)
    return ds


@router.get("/{dataset_id}")
def get_dataset(dataset_id: str, session: SessionDep, t: TDep) -> dict:
    return dataset_out(_get(session, dataset_id), t)


@router.get("/{dataset_id}/profile")
def get_profile(dataset_id: str, session: SessionDep, t: TDep) -> dict:
    ds = _get(session, dataset_id)
    ready = ds.status in (DatasetStatus.PROFILED, DatasetStatus.CLEANED)
    profile = svc.load_profile(ds) if ready else None
    if profile is None:
        raise ProblemError(409, "dataset.not_ready")
    columns = []
    for c in profile["columns_profile"]:
        col = {k: v for k, v in c.items() if k != "text_weight"}
        col["label"] = t(f"fields.{c['canonical_field']}.label") if c["canonical_field"] else None
        col["candidate_labels"] = {name: t(f"fields.{name}.label") for name in c["candidates"]}
        col["pii_label"] = t(f"pii.{c['pii_kind']}") if c["pii_kind"] else None
        columns.append(col)
    return {
        "dataset": dataset_out(ds, t),
        "read": profile.get("read"),
        "size_bytes": profile.get("size_bytes"),
        "rows": profile["rows"],
        "columns_count": profile["columns"],
        "duplicate_rows": profile["duplicate_rows"],
        "duplicate_keys": profile["duplicate_keys"],
        "invalid_rows": profile.get("invalid_rows", 0),
        "inconsistent_rows": profile.get("inconsistent_rows", 0),
        "data_lang": profile["data_lang"],
        "data_lang_label": profile["data_lang_label"],
        "quality": profile["quality"],
        "pii": [
            {"field": c["source_header"], "kind": c["pii_kind"], "label": c["pii_label"]}
            for c in columns
            if c["pii_kind"]
        ],
        "storage": {"raw": "parquet", "staged": "parquet"},
        "is_seed": ds.source == DatasetSource.SEED,
        "columns": columns,
    }


@router.get("/{dataset_id}/issues")
def get_issues(dataset_id: str, session: SessionDep, t: TDep) -> dict:
    """Issue cards for the Cleaning Studio (machine fields + localized texts)."""
    ds = _get(session, dataset_id)
    if ds.status not in (DatasetStatus.PROFILED, DatasetStatus.CLEANED):
        raise ProblemError(409, "dataset.not_ready")
    profile = svc.load_profile(ds) or {}
    data = cleaning.localized_issues(ds, t)
    after = (ds.profile_json or {}).get("quality_after")
    return {
        "dataset": dataset_out(ds, t),
        "quality": profile.get("quality"),
        "quality_after": after,
        "columns": data["columns"],
        "issues": data["issues"],
        "op_labels": {op: t(f"recipes.ops.{op}") for op in OPERATIONS},
    }


class ApplyRecipeBody(BaseModel):
    recipe_id: uuid.UUID | None = None
    recipe: RecipeInput | None = None


@router.post("/{dataset_id}/recipes/apply", status_code=202)
def apply_recipe(
    dataset_id: str, body: ApplyRecipeBody, background: BackgroundTasks, session: SessionDep
) -> JSONResponse:
    ds = _get(session, dataset_id)
    if body.recipe_id:
        recipe = session.get(Recipe, body.recipe_id)
        if recipe is None:
            raise ProblemError(404, "recipe.not_found", recipe_id=str(body.recipe_id))
        steps, recipe_id = recipe.steps_json, str(recipe.id)
    elif body.recipe:
        steps, recipe_id = validated(body.recipe.steps), None
    else:
        raise ProblemError(422, "request.invalid", fields=["recipe_id", "recipe"])
    job = Job(
        type=JobType.APPLY_RECIPE,
        status=JobStatus.QUEUED,
        dataset_id=ds.id,
        input_json={"recipe_id": recipe_id, "steps": steps},
    )
    session.add(job)
    session.commit()
    background.add_task(cleaning.run_apply_job, job.id)
    return JSONResponse(
        {"id": str(job.id), "status": job.status.value},
        status_code=202,
        headers={"Location": f"/api/v1/jobs/{job.id}"},
    )
