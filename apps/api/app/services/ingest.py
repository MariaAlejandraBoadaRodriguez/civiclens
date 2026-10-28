"""Ingest pipeline: bytes → raw Parquet → profile → staged Parquet (canonical names).

Staged keeps every value exactly as written; only headers are renamed to the canonical
schema. Parsing numbers/dates/currencies is a user decision in the Cleaning Studio
(slice 5b), so nothing is silently changed here.
"""

from __future__ import annotations

import uuid
from typing import Any

import pandas as pd

from app.core.ingest.detect import encoding_label
from app.core.ingest.reader import read_any
from app.core.profile.profiler import profile_frame
from app.services import storage


def staged_frame(raw: pd.DataFrame, columns: list[dict[str, Any]]) -> pd.DataFrame:
    """Rename mapped columns to their canonical field; unmapped columns keep their name."""
    rename: dict[str, str] = {}
    used: set[str] = set()
    for col in columns:
        target = col["canonical_field"] or col["source_header"]
        if target in used:
            target = f"{target}__{col['source_header']}"
        used.add(target)
        rename[col["source_header"]] = target
    return raw.rename(columns=rename)


def ingest_bytes(dataset_id: uuid.UUID, data: bytes, filename: str) -> dict[str, Any]:
    """Run the full pipeline and persist its outputs. Returns the profile document."""
    raw, info = read_any(data, filename)
    storage.write_parquet(raw, storage.raw_path(dataset_id))
    profile = profile_frame(raw)
    staged = staged_frame(raw, profile["columns_profile"])
    storage.write_parquet(staged, storage.staged_path(dataset_id))
    read = info.to_dict()
    read["format"] = str(read["format"])
    read["encoding_label"] = encoding_label(read["encoding"]) if read.get("encoding") else None
    profile["read"] = read
    profile["size_bytes"] = len(data)
    storage.write_json(profile, storage.profile_path(dataset_id))
    return profile
