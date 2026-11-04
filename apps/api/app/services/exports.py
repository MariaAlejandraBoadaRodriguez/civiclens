"""Files a user downloads: the cleaned data as CSV or Parquet."""

from __future__ import annotations

from pathlib import Path

from app.core import memory
from app.db.models import Dataset
from app.services import storage


def cleaned_file(ds: Dataset, fmt: str) -> tuple[Path, str]:
    """Path of the cleaned data in ``fmt`` (cached next to the dataset) and its origin:
    ``clean`` (the applied recipe) or ``recommended`` (recommended options, on the fly).
    The cache is keyed on the clean layer's modification time, so a new recipe invalidates it."""
    from app.services.sql import source_frame

    clean = storage.clean_path(ds.id)
    origin = "clean" if clean.exists() else "recommended"
    if fmt == "parquet" and origin == "clean":
        return clean, origin
    stamp = int(clean.stat().st_mtime) if clean.exists() else 0
    out = storage.dataset_dir(ds.id) / f"download-{origin}-{stamp}.{fmt}"
    if not out.exists():
        frame, _ = source_frame(ds)
        tmp = out.with_suffix(".tmp")
        if fmt == "csv":
            frame.to_csv(tmp, index=False)
        else:
            frame.astype("string").to_parquet(tmp, index=False, compression="zstd")
        tmp.replace(out)
        del frame
        memory.release()
    return out, origin
