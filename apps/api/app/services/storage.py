"""On-disk layout of a dataset: original file, raw + staged Parquet, profile JSON."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

import pandas as pd

from app.config import settings


def dataset_dir(dataset_id: uuid.UUID) -> Path:
    path = settings.data_dir / "datasets" / str(dataset_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def original_path(dataset_id: uuid.UUID, filename: str) -> Path:
    suffix = Path(filename).suffix.lower()[:8] or ".bin"
    return dataset_dir(dataset_id) / f"original{suffix}"


def raw_path(dataset_id: uuid.UUID) -> Path:
    return dataset_dir(dataset_id) / "raw.parquet"


def staged_path(dataset_id: uuid.UUID) -> Path:
    return dataset_dir(dataset_id) / "staged.parquet"


def profile_path(dataset_id: uuid.UUID) -> Path:
    return dataset_dir(dataset_id) / "profile.json"


def issues_path(dataset_id: uuid.UUID) -> Path:
    return dataset_dir(dataset_id) / "issues.json"


def clean_path(dataset_id: uuid.UUID) -> Path:
    return dataset_dir(dataset_id) / "clean.parquet"


def star_path(dataset_id: uuid.UUID) -> Path:
    return dataset_dir(dataset_id) / "star.duckdb"


def clean_profile_path(dataset_id: uuid.UUID) -> Path:
    return dataset_dir(dataset_id) / "profile_clean.json"


def write_parquet(df: pd.DataFrame, path: Path, as_text: bool = True) -> None:
    """Raw/staged layers are stored as nullable strings (never coerced); the clean layer
    keeps the types the recipe produced (``as_text=False``)."""
    (df.astype("string") if as_text else df).to_parquet(path, index=False, compression="zstd")


def read_parquet(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path).astype(object)
    return df.where(df.notna(), None)


def write_json(data: dict[str, Any], path: Path) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)  # atomic: readers never see a half-written profile


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def delete_dataset_files(dataset_id: uuid.UUID) -> None:
    shutil.rmtree(settings.data_dir / "datasets" / str(dataset_id), ignore_errors=True)
