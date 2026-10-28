"""Dataset lifecycle: seed registration, uploads, ingest jobs, lookups and expiry."""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.ingest.detect import UnsupportedFormatError
from app.core.ingest.language import dominant
from app.core.ingest.reader import EmptyFileError
from app.core.seed.dirty import DIRTY_BUILDERS
from app.core.seed.registry import SEEDS, Seed
from app.db.models import (
    DataLanguage,
    Dataset,
    DatasetFormat,
    DatasetSource,
    DatasetStatus,
    Job,
    JobStatus,
    JobType,
)
from app.db.session import SessionLocal
from app.services import storage
from app.services.ingest import ingest_bytes

log = logging.getLogger(__name__)
_seed_locks: dict[str, threading.Lock] = {slug: threading.Lock() for slug in SEEDS}


def now() -> datetime:
    return datetime.now(UTC)


def _apply_profile(ds: Dataset, profile: dict[str, Any]) -> None:
    ds.rows = profile["rows"]
    ds.columns = profile["columns"]
    ds.quality_score = profile["quality"]["score"]
    label = dominant(profile["data_lang"])
    ds.data_lang = DataLanguage(label)
    ds.status = DatasetStatus.PROFILED
    ds.raw_path = str(storage.raw_path(ds.id))
    ds.staged_path = str(storage.staged_path(ds.id))
    ds.profile_json = {
        "quality": profile["quality"],
        "data_lang": profile["data_lang"],
        "read": profile.get("read"),
    }


# --------------------------------------------------------------------------- seeds


def ensure_seed(session: Session, seed: Seed) -> Dataset:
    """Return the seed's dataset row, building its demo file + profile on first use."""
    ds = session.get(Dataset, seed.id)
    if ds and ds.status == DatasetStatus.PROFILED and storage.profile_path(seed.id).exists():
        return ds
    with _seed_locks[seed.slug]:
        session.expire_all()
        ds = session.get(Dataset, seed.id)
        if ds and ds.status == DatasetStatus.PROFILED and storage.profile_path(seed.id).exists():
            return ds
        if ds is None:
            ds = Dataset(
                id=seed.id,
                slug=seed.slug,
                name=seed.slug,
                source=DatasetSource.SEED,
                format=DatasetFormat(seed.format),
            )
            session.add(ds)
            session.commit()
        result = DIRTY_BUILDERS[seed.slug](pd.read_parquet(settings.seed_dir / seed.parquet))
        storage.original_path(seed.id, result.filename).write_bytes(result.data)
        profile = ingest_bytes(seed.id, result.data, result.filename)
        profile["dirty_manifest"] = result.manifest
        storage.write_json(profile, storage.profile_path(seed.id))
        _apply_profile(ds, profile)
        session.commit()
        log.info("seed %s ready: %s rows", seed.slug, ds.rows)
        return ds


def warm_seeds() -> None:
    """Build all demo datasets (called in a background thread at startup)."""
    for seed in SEEDS.values():
        try:
            with SessionLocal() as session:
                ensure_seed(session, seed)
        except Exception:  # noqa: BLE001 — warming is best effort; requests retry lazily
            log.exception("could not warm seed %s", seed.slug)


# --------------------------------------------------------------------------- lookups


def resolve(session: Session, ref: str) -> Dataset | None:
    """Find a dataset by seed slug or UUID; seeds are built on demand. Expired → None."""
    if ref in SEEDS:
        return ensure_seed(session, SEEDS[ref])
    try:
        dataset_id = uuid.UUID(ref)
    except ValueError:
        return None
    seed = next((s for s in SEEDS.values() if s.id == dataset_id), None)
    if seed:
        return ensure_seed(session, seed)
    ds = session.get(Dataset, dataset_id)
    if ds is None or (ds.expires_at and _aware(ds.expires_at) < now()):
        return None
    return ds


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def list_datasets(session: Session) -> list[Dataset]:
    seeds = [ensure_seed(session, s) for s in SEEDS.values()]
    uploads = session.scalars(
        select(Dataset)
        .where(Dataset.source != DatasetSource.SEED, Dataset.status != DatasetStatus.EXPIRED)
        .order_by(Dataset.created_at.desc())
        .limit(50)
    ).all()
    return seeds + [d for d in uploads if not d.expires_at or _aware(d.expires_at) > now()]


def load_profile(ds: Dataset) -> dict[str, Any] | None:
    return storage.read_json(storage.profile_path(ds.id))


# --------------------------------------------------------------------------- uploads


def create_upload(
    session: Session, filename: str, data: bytes, fmt: str, name: str | None
) -> tuple[Dataset, Job]:
    ds = Dataset(
        name=(name or filename)[:255],
        source=DatasetSource.UPLOAD,
        format=DatasetFormat(fmt),
        status=DatasetStatus.UPLOADED,
        expires_at=now() + timedelta(hours=settings.upload_ttl_hours),
    )
    session.add(ds)
    session.flush()
    path = storage.original_path(ds.id, filename)
    path.write_bytes(data)
    ds.raw_path = str(path)
    job = Job(
        type=JobType.INGEST,
        status=JobStatus.QUEUED,
        dataset_id=ds.id,
        input_json={"filename": filename},
    )
    session.add(job)
    session.commit()
    return ds, job


def run_ingest_job(job_id: uuid.UUID) -> None:
    """Background task: ingest + profile one upload, recording the outcome on the job."""
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        if job is None or job.dataset_id is None:
            return
        ds = session.get(Dataset, job.dataset_id)
        job.status, job.started_at = JobStatus.RUNNING, now()
        session.commit()
        try:
            filename = (job.input_json or {}).get("filename", "upload")
            data = storage.original_path(ds.id, filename).read_bytes()
            profile = ingest_bytes(ds.id, data, filename)
            _apply_profile(ds, profile)
            job.status = JobStatus.SUCCEEDED
            job.result_json = {
                "dataset_id": str(ds.id),
                "rows": ds.rows,
                "quality_score": ds.quality_score,
            }
        except (UnsupportedFormatError, EmptyFileError) as exc:
            job.status, job.error_code, ds.status = JobStatus.FAILED, exc.code, DatasetStatus.FAILED
        except Exception:  # noqa: BLE001 — any parser crash becomes a stable, localized code
            log.exception("ingest job %s failed", job_id)
            job.status, job.error_code, ds.status = (
                JobStatus.FAILED,
                "ingest.unreadable",
                DatasetStatus.FAILED,
            )
        job.finished_at = now()
        session.commit()


def purge_expired(session: Session) -> int:
    """Delete files of uploads past their TTL and mark them expired (24 h policy)."""
    expired = session.scalars(
        select(Dataset).where(
            Dataset.source == DatasetSource.UPLOAD,
            Dataset.status != DatasetStatus.EXPIRED,
            Dataset.expires_at < now(),
        )
    ).all()
    for ds in expired:
        storage.delete_dataset_files(ds.id)
        ds.status = DatasetStatus.EXPIRED
    session.commit()
    return len(expired)
