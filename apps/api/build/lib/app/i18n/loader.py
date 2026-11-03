"""Load ``app/i18n/{en,es}/*.yaml`` and resolve dotted keys with ``{placeholder}`` params.

The file name is the first key segment: ``fields.yaml`` → ``fields.signed_date.label``.
Missing keys fall back to English, then to the key itself (never crash a response).
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

import yaml

CATALOG_DIR = Path(__file__).resolve().parent
SUPPORTED = ("en", "es")
DEFAULT = "en"


def _flatten(node: Any, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    if isinstance(node, dict):
        for key, value in node.items():
            out.update(_flatten(value, f"{prefix}.{key}" if prefix else str(key)))
    else:
        out[prefix] = str(node)
    return out


@cache
def catalog(lang: str) -> dict[str, str]:
    entries: dict[str, str] = {}
    for path in sorted((CATALOG_DIR / lang).glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        entries.update(_flatten(data, path.stem))
    return entries


def negotiate(accept_language: str | None) -> str:
    """Best supported language from an ``Accept-Language`` header (q-values honoured)."""
    if not accept_language:
        return DEFAULT
    ranked: list[tuple[float, int, str]] = []
    for i, part in enumerate(accept_language.split(",")):
        piece = part.strip()
        if not piece:
            continue
        lang, _, params = piece.partition(";")
        q = 1.0
        if params.strip().startswith("q="):
            try:
                q = float(params.strip()[2:])
            except ValueError:
                q = 0.0
        ranked.append((-q, i, lang.strip().lower()))
    for _, _, lang in sorted(ranked):
        base = lang.split("-")[0]
        if base in SUPPORTED:
            return base
    return DEFAULT


class Translator:
    def __init__(self, lang: str) -> None:
        self.lang = lang if lang in SUPPORTED else DEFAULT

    def __call__(self, key: str, **params: Any) -> str:
        text = catalog(self.lang).get(key) or catalog(DEFAULT).get(key) or key
        try:
            return text.format(**params) if params else text
        except (KeyError, IndexError):
            return text

    def has(self, key: str) -> bool:
        return key in catalog(self.lang)
