"""Small HTTP header helpers."""

from __future__ import annotations

import re
from urllib.parse import quote

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def content_disposition(disposition: str, filename: str) -> str:
    """``Content-Disposition`` that is always latin-1 safe (RFC 6266 / RFC 5987).

    Starlette encodes headers as latin-1, so a recipe called "Nettoyage — été" would crash the
    response. The plain ``filename`` is an ASCII fallback; ``filename*`` carries the real name.
    """
    stem, dot, ext = filename.rpartition(".")
    if not dot:
        stem, ext = filename, ""
    ascii_stem = re.sub("_+", "_", _UNSAFE.sub("_", stem)).strip("_") or "download"
    fallback = f"{ascii_stem}.{ext}" if ext else ascii_stem
    value = f'{disposition}; filename="{fallback}"'
    if fallback != filename:
        value += f"; filename*=UTF-8''{quote(filename, safe='')}"
    return value
