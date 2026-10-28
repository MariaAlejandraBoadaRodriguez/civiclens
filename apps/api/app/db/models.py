"""SQLAlchemy 2 models for the application database (ADR-0003).

Transactional data only: API keys, datasets metadata, recipes, jobs and the audit log.
Contract data itself lives in Parquet + DuckDB (ADR-0002). Types are portable
(Uuid, JSON→JSONB on Postgres) so migrations are also testable on SQLite.
Errors are stored as stable codes and rendered in the requested language (ADR-0007).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Deterministic constraint names → stable, reviewable migrations.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

JsonDoc = JSON().with_variant(JSONB(), "postgresql")
BigId = BigInteger().with_variant(Integer(), "sqlite")


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    # VARCHAR + CHECK instead of a native PG enum: adding a value is a plain migration.
    return Enum(
        cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
    )


class DataLanguage(enum.StrEnum):
    EN = "en"
    FR = "fr"
    ES = "es"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class DatasetFormat(enum.StrEnum):
    CSV = "csv"
    XLSX = "xlsx"
    JSON = "json"
    PARQUET = "parquet"


class DatasetSource(enum.StrEnum):
    SEED = "seed"
    UPLOAD = "upload"
    API = "api"


class DatasetStatus(enum.StrEnum):
    UPLOADED = "uploaded"
    PROFILED = "profiled"
    CLEANED = "cleaned"
    MODELED = "modeled"
    FAILED = "failed"
    EXPIRED = "expired"


class JobType(enum.StrEnum):
    INGEST = "ingest"
    PROFILE = "profile"
    APPLY_RECIPE = "apply_recipe"
    BUILD_SCHEMA = "build_schema"
    MODEL_RUN = "model_run"
    REPORT = "report"


class JobStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ApiKey(TimestampMixin, Base):
    """Agency API key. Only the argon2 hash is stored; the full key is shown once."""

    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Public, non-secret lookup prefix (e.g. "cl_live_ab12cd34") — avoids hashing against every row.
    prefix: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    hash: Mapped[str] = mapped_column(String(255), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JsonDoc, nullable=False, default=list)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    jobs: Mapped[list[Job]] = relationship(back_populates="api_key")


class Dataset(TimestampMixin, Base):
    """Metadata of a seed or uploaded dataset. Files live on disk as Parquet (raw + staged)."""

    __tablename__ = "datasets"
    __table_args__ = (
        CheckConstraint(
            "quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 100)",
            name="quality_score_range",
        ),
        Index("ix_datasets_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Stable slug for seed datasets (e.g. "secop_co"); NULL for uploads.
    slug: Mapped[str | None] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[DatasetSource] = mapped_column(_enum(DatasetSource, "dataset_source"))
    format: Mapped[DatasetFormat] = mapped_column(_enum(DatasetFormat, "dataset_format"))
    data_lang: Mapped[DataLanguage] = mapped_column(
        _enum(DataLanguage, "data_language"), default=DataLanguage.UNKNOWN
    )
    status: Mapped[DatasetStatus] = mapped_column(
        _enum(DatasetStatus, "dataset_status"), default=DatasetStatus.UPLOADED
    )
    rows: Mapped[int | None] = mapped_column(BigInteger)
    columns: Mapped[int | None] = mapped_column(Integer)
    quality_score: Mapped[int | None] = mapped_column(Integer)
    raw_path: Mapped[str | None] = mapped_column(Text)
    staged_path: Mapped[str | None] = mapped_column(Text)
    # Per-column profile incl. detected data language and header mapping (machine fields only).
    profile_json: Mapped[dict[str, Any] | None] = mapped_column(JsonDoc)
    # NULL for seed data (permanent); uploads expire after 24 h (ROADMAP A3).
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    recipes: Mapped[list[Recipe]] = relationship(back_populates="dataset")
    jobs: Mapped[list[Job]] = relationship(back_populates="dataset")


class Recipe(TimestampMixin, Base):
    """Versioned cleaning recipe. Outlives the upload it was built on (FK → SET NULL)."""

    __tablename__ = "recipes"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_recipes_name_version"),
        CheckConstraint("version >= 1", name="version_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("datasets.id", ondelete="SET NULL"), index=True
    )
    steps_json: Mapped[list[dict[str, Any]]] = mapped_column(JsonDoc, nullable=False)

    dataset: Mapped[Dataset | None] = relationship(back_populates="recipes")


class Job(TimestampMixin, Base):
    """Async work tracked in Postgres (no queue service; ROADMAP §2)."""

    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_status_created_at", "status", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    type: Mapped[JobType] = mapped_column(_enum(JobType, "job_type"))
    status: Mapped[JobStatus] = mapped_column(
        _enum(JobStatus, "job_status"), default=JobStatus.QUEUED
    )
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("api_keys.id", ondelete="SET NULL")
    )
    input_json: Mapped[dict[str, Any] | None] = mapped_column(JsonDoc)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JsonDoc)
    # Stable machine code (e.g. "ingest.unsupported_encoding"); localized at read time.
    error_code: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    dataset: Mapped[Dataset | None] = relationship(back_populates="jobs")
    api_key: Mapped[ApiKey | None] = relationship(back_populates="jobs")


class AuditLog(Base):
    """Append-only log: who did what to which target (cleaning decisions, key changes)."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_target_at", "target", "at"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[str] = mapped_column(String(255), nullable=False)
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JsonDoc)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
