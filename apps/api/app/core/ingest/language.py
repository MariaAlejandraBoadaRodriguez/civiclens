"""Data-language detection (EN / FR / ES) from cell values and headers.

A small stop-word + character model instead of a general-purpose detector: we only need
three languages, it is deterministic (same input → same answer, no random seed), fast on
50k rows, and explainable. Short or numeric cells are ignored.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from enum import StrEnum

from app.core.ingest.locale_parse import strip_accents


class Language(StrEnum):
    EN = "en"
    FR = "fr"
    ES = "es"


STOPWORDS: dict[Language, frozenset[str]] = {
    Language.EN: frozenset(
        "the and of to for in on with by from services service other not elsewhere specified "
        "professional contract contracts supply equipment management support for of".split()
    ),
    Language.FR: frozenset(
        "le la les des du de et pour en au aux une un sur par avec dans services service autres "
        "travaux contrat fourniture entretien gestion ailleurs non specifies professionnels".split()
    ),
    Language.ES: frozenset(
        "el la los las del de y para en con por al una un sus su servicios servicio prestacion "
        "contrato suministro apoyo gestion profesionales mantenimiento obra adquisicion".split()
    ),
}
# Words shared by FR and ES ("de", "la", "en") still count for both; distinctive ones decide.
_CHARS: dict[Language, str] = {Language.ES: "ñ¿¡", Language.FR: "çèêëàâîïôûœ"}
_WORD = re.compile(r"[a-zà-ÿñ]+", re.IGNORECASE)


def score_text(text: str) -> Counter[Language]:
    scores: Counter[Language] = Counter()
    lowered = text.lower()
    for lang, chars in _CHARS.items():
        hits = sum(lowered.count(c) for c in chars)
        if hits:
            scores[lang] += 2 * hits
    for word in _WORD.findall(strip_accents(lowered)):
        for lang, words in STOPWORDS.items():
            if word in words:
                scores[lang] += 1
    return scores


def detect_text(text: str) -> Language | None:
    """Language of one cell, or None when there is no signal or a tie."""
    if not text or len(text) < 4 or not any(ch.isalpha() for ch in text):
        return None
    ranked = score_text(text).most_common(2)
    if not ranked or (len(ranked) == 2 and ranked[0][1] == ranked[1][1]):
        return None
    return ranked[0][0]


def detect_values(values: Iterable[object], sample: int = 400) -> dict[str, float]:
    """Share of each language among cells with a clear signal, e.g. ``{"es": 0.98, "en": 0.02}``.
    Empty dict when the column has no linguistic content (codes, numbers, dates)."""
    counts: Counter[str] = Counter()
    seen = 0
    for value in values:
        if seen >= sample:
            break
        if value is None or not isinstance(value, str):
            continue
        seen += 1
        lang = detect_text(value)
        if lang:
            counts[lang.value] += 1
    total = sum(counts.values())
    if total == 0 or total < max(3, seen * 0.2):
        return {}
    return {k: round(v / total, 3) for k, v in counts.most_common()}


def combine(shares: Iterable[tuple[dict[str, float], float]]) -> dict[str, float]:
    """Weighted merge of per-column shares (weight = number of text cells)."""
    acc: Counter[str] = Counter()
    for share, weight in shares:
        for lang, value in share.items():
            acc[lang] += value * weight
    total = sum(acc.values())
    return {k: round(v / total, 3) for k, v in acc.most_common()} if total else {}


def dominant(shares: dict[str, float], threshold: float = 0.8) -> str:
    """Single language if it dominates, ``mixed`` if several, ``unknown`` if none."""
    if not shares:
        return "unknown"
    lang, share = max(shares.items(), key=lambda kv: kv[1])
    return lang if share >= threshold else "mixed"
