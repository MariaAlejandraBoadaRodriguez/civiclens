"""On-disk layout of a dataset: original file, raw + staged Parquet, profile JSON."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

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


def upload_tmp_path() -> Path:
    """A fresh temporary file for an upload being streamed in (same disk as the datasets)."""
    folder = settings.data_dir / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{uuid.uuid4().hex}.part"


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
    """Raw/staged layer as object columns with ``None`` for nulls.

    Text columns are read through Arrow's dictionary encoding, so every distinct value is one
    Python string shared by all its cells: about half the memory of one string per cell (on the
    25,000-row SECOP seed, 58 MB instead of 131 MB), with an identical frame."""
    parquet = pq.ParquetFile(path)
    columns: dict[str, np.ndarray] = {}
    for name in parquet.schema_arrow.names:
        column = parquet.read(columns=[name]).column(0)
        if pa.types.is_string(column.type) or pa.types.is_large_string(column.type):
            encoded = column.dictionary_encode().combine_chunks()
            values = np.array([*encoded.dictionary.to_pylist(), None], dtype=object)
            codes = encoded.indices.fill_null(len(values) - 1).to_numpy(zero_copy_only=False)
            columns[name] = values[codes]
        else:
            series = column.to_pandas().astype(object)
            columns[name] = series.where(series.notna(), None).to_numpy(dtype=object)
    return pd.DataFrame(columns, index=pd.RangeIndex(parquet.metadata.num_rows), dtype=object)


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
