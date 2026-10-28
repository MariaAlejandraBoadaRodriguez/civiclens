"""Read CSV / XLSX / JSON / Parquet bytes into an all-string DataFrame ("raw" layer).

Nothing is cleaned here: values stay exactly as written (only decoded). Missing cells
are ``None``. Detection results are returned alongside for the profile screen.
"""

from __future__ import annotations

import io
import json
from dataclasses import asdict, dataclass

import pandas as pd

from app.core.ingest.detect import (
    FileFormat,
    UnsupportedFormatError,
    detect_delimiter,
    detect_encoding,
    detect_format,
    detect_header_row,
    json_records_path,
)


@dataclass
class ReadInfo:
    format: str
    encoding: str | None = None
    delimiter: str | None = None
    sheet: str | None = None
    header_row: int = 0
    records_path: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class EmptyFileError(ValueError):
    code = "ingest.empty_file"


def _unique_headers(raw: list[object]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for i, h in enumerate(raw):
        name = (
            str(h).strip()
            if h is not None and str(h).strip() and str(h) != "nan"
            else f"column_{i + 1}"
        )
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 1
        out.append(name)
    return out


def _as_strings(df: pd.DataFrame) -> pd.DataFrame:
    def cell(v: object) -> str | None:
        if v is None or (isinstance(v, float) and v != v):
            return None
        if isinstance(v, list | dict):
            return json.dumps(v, ensure_ascii=False, sort_keys=True)
        return str(v)

    out = pd.DataFrame({c: [cell(v) for v in df[c].tolist()] for c in df.columns}, dtype=object)
    return out.reset_index(drop=True)


def _from_rows(rows: list[list[object]]) -> tuple[pd.DataFrame, int]:
    header_idx = detect_header_row([[("" if c is None else str(c)) for c in r] for r in rows])
    header = _unique_headers(rows[header_idx])
    body = [list(r) + [None] * (len(header) - len(r)) for r in rows[header_idx + 1 :]]
    body = [r[: len(header)] for r in body if any(c not in (None, "") for c in r)]
    return pd.DataFrame(body, columns=header, dtype=object), header_idx


def read_csv_bytes(data: bytes) -> tuple[pd.DataFrame, ReadInfo]:
    encoding = detect_encoding(data)
    text = data.decode(encoding)
    delimiter = detect_delimiter(text[:200_000])
    frame = pd.read_csv(
        io.StringIO(text),
        sep=delimiter,
        header=None,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
        skip_blank_lines=True,
        engine="python" if len(delimiter) > 1 else "c",
    )
    rows = frame.astype(object).values.tolist()
    df, header_row = _from_rows(rows)
    info = ReadInfo(FileFormat.CSV, encoding=encoding, delimiter=delimiter, header_row=header_row)
    return _as_strings(df), info


def read_xlsx_bytes(data: bytes) -> tuple[pd.DataFrame, ReadInfo]:
    sheets = pd.read_excel(
        io.BytesIO(data), sheet_name=None, header=None, dtype=object, engine="openpyxl"
    )
    if not sheets:
        raise EmptyFileError("xlsx")
    name, frame = max(sheets.items(), key=lambda kv: kv[1].dropna(how="all").shape[0])
    rows = frame.astype(object).where(frame.notna(), None).values.tolist()
    if not any(any(c is not None for c in r) for r in rows):
        raise EmptyFileError("xlsx")
    df, header_row = _from_rows(rows)
    return _as_strings(df), ReadInfo(FileFormat.XLSX, sheet=str(name), header_row=header_row)


def read_json_bytes(data: bytes) -> tuple[pd.DataFrame, ReadInfo]:
    encoding = detect_encoding(data)
    payload = json.loads(data.decode(encoding))
    path = json_records_path(payload)
    if path is None:
        raise UnsupportedFormatError("json")
    records = payload if path == "" else payload[path]
    if not records:
        raise EmptyFileError("json")
    df = pd.json_normalize(records, sep=".", max_level=3)
    return _as_strings(df), ReadInfo(FileFormat.JSON, encoding=encoding, records_path=path or None)


def read_parquet_bytes(data: bytes) -> tuple[pd.DataFrame, ReadInfo]:
    df = pd.read_parquet(io.BytesIO(data))
    return _as_strings(df), ReadInfo(FileFormat.PARQUET)


READERS = {
    FileFormat.CSV: read_csv_bytes,
    FileFormat.XLSX: read_xlsx_bytes,
    FileFormat.JSON: read_json_bytes,
    FileFormat.PARQUET: read_parquet_bytes,
}


def read_any(data: bytes, filename: str) -> tuple[pd.DataFrame, ReadInfo]:
    if not data.strip():
        raise EmptyFileError(filename)
    fmt = detect_format(filename, data[:8192])
    df, info = READERS[fmt](data)
    if df.empty or df.shape[1] == 0:
        raise EmptyFileError(filename)
    return df, info
