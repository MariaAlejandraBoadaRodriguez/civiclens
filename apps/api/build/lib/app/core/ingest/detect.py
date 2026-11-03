"""File-level detection: format, text encoding, CSV delimiter and header row. Pure functions."""

from __future__ import annotations

import csv
import io
import json
from collections import Counter
from enum import StrEnum


class FileFormat(StrEnum):
    CSV = "csv"
    XLSX = "xlsx"
    JSON = "json"
    PARQUET = "parquet"


class UnsupportedFormatError(ValueError):
    """Raised with a stable code; the API renders it as a localized RFC 7807 problem."""

    code = "ingest.unsupported_format"


_ZIP_MAGIC = b"PK\x03\x04"
_PARQUET_MAGIC = b"PAR1"
_OLE_MAGIC = b"\xd0\xcf\x11\xe0"  # legacy .xls / macro containers — rejected


def detect_format(filename: str, head: bytes) -> FileFormat:
    """Sniff the content first; the extension only breaks ties. Rejects .xls/.xlsm."""
    name = filename.lower()
    if head.startswith(_PARQUET_MAGIC):
        return FileFormat.PARQUET
    if head.startswith(_OLE_MAGIC) or name.endswith((".xls", ".xlsm", ".xlsb")):
        raise UnsupportedFormatError(filename)
    if head.startswith(_ZIP_MAGIC):
        if name.endswith(".xlsx") or b"xl/" in head[:4096] or b"[Content_Types].xml" in head[:4096]:
            return FileFormat.XLSX
        raise UnsupportedFormatError(filename)
    stripped = head.lstrip(b"\xef\xbb\xbf \t\r\n")
    if stripped[:1] in (b"{", b"["):
        return FileFormat.JSON
    if b"\x00" in head[:4096]:
        raise UnsupportedFormatError(filename)  # binary we do not know
    return FileFormat.CSV


# Order matters: utf-8 is strict, so if it decodes it is almost certainly right.
_ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")


def detect_encoding(data: bytes) -> str:
    """Return a Python codec name that decodes ``data`` (``latin-1`` always succeeds)."""
    for encoding in _ENCODINGS[:2]:
        try:
            data.decode(encoding)
        except UnicodeDecodeError:
            continue
        return "utf-8-sig" if data.startswith(b"\xef\xbb\xbf") else "utf-8"
    try:
        data.decode("cp1252")
        return "cp1252"
    except UnicodeDecodeError:
        return "latin-1"


def encoding_label(encoding: str) -> str:
    """Human-friendly label shown in the UI (data, not translated)."""
    return {
        "utf-8": "UTF-8",
        "utf-8-sig": "UTF-8 (BOM)",
        "cp1252": "Windows-1252",
        "latin-1": "Latin-1",
    }[encoding]


_DELIMITERS = (",", ";", "\t", "|")


def detect_delimiter(sample: str) -> str:
    """Delimiter whose per-line field count is the most consistent (ties → most fields)."""
    lines = [line for line in sample.splitlines()[:50] if line.strip()]
    if not lines:
        return ","
    best, best_score = ",", (-1.0, 0)
    for delim in _DELIMITERS:
        rows = list(csv.reader(io.StringIO("\n".join(lines)), delimiter=delim))
        counts = [len(r) for r in rows]
        if not counts or max(counts) < 2:
            continue
        mode, freq = Counter(counts).most_common(1)[0]
        score = (freq / len(counts), mode)
        if score > best_score:
            best, best_score = delim, score
    return best


def detect_header_row(rows: list[list[str]], max_scan: int = 10) -> int:
    """Index of the first row that looks like a header: ≥ 2 non-empty cells, mostly
    non-numeric, and with as many cells as the following data rows. Title rows above
    a table (common in government exports) are skipped."""
    if not rows:
        return 0
    widths = Counter(len([c for c in r if str(c).strip()]) for r in rows[: max_scan + 20])
    table_width = widths.most_common(1)[0][0]
    for i, row in enumerate(rows[:max_scan]):
        cells = [str(c).strip() for c in row if str(c).strip()]
        if len(cells) < max(2, int(table_width * 0.8)):
            continue
        textual = sum(1 for c in cells if not _looks_numeric(c))
        if textual / len(cells) >= 0.8:
            return i
    return 0


def _looks_numeric(cell: str) -> bool:
    return (
        cell.replace(".", "").replace(",", "").replace("-", "").replace("/", "").strip().isdigit()
    )


def json_records_path(payload: object) -> str | None:
    """Locate the list of records inside a JSON document: the root list, or the largest
    list of objects one level down (e.g. OCDS ``{"releases": [...]}``)."""
    if isinstance(payload, list):
        return ""
    if isinstance(payload, dict):
        candidates = [
            (len(v), k)
            for k, v in payload.items()
            if isinstance(v, list) and v and isinstance(v[0], dict)
        ]
        if candidates:
            return max(candidates)[1]
    return None


def peek_json(data: bytes, encoding: str) -> object:
    return json.loads(data.decode(encoding))
