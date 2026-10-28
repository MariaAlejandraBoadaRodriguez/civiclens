"""Personal-data scan (emails, phone numbers, national ID numbers, person names).

Value patterns plus header hints in EN / FR / ES. A column is flagged when enough of
its non-null values match; masking replaces values with a stable hash (slice 5b op).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from enum import StrEnum

from app.core.ingest.headers_map import normalize_header
from app.core.ingest.locale_parse import parse_date


class PiiKind(StrEnum):
    EMAIL = "email"
    PHONE = "phone"
    NATIONAL_ID = "national_id"
    PERSON_NAME = "person_name"


EMAIL = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")
PHONE = re.compile(r"^\+?[\d\s().-]{7,20}$")
ID_NUMBER = re.compile(r"^\d{6,12}$")
DATE_LIKE = re.compile(r"^\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}")

PHONE_HINTS = ("tel", "telefono", "phone", "celular", "movil", "mobile", "telephone", "cellulaire")
ID_HINTS = (
    "cedula",
    "documento",
    "identificacion",
    "num_doc",
    "dni",
    "sin",
    "nas",
    "passport",
    "pasaporte",
    "id_number",
    "numero_identite",
)
NAME_HINTS = (
    "representante",
    "nombre_contacto",
    "contact_name",
    "nom_contact",
    "supervisor",
    "ordenador",
    "person_name",
    "nombre_persona",
    "responsable",
)


def _hint(header: str, hints: tuple[str, ...]) -> bool:
    tokens = set(normalize_header(header).split("_"))
    norm = normalize_header(header)
    return any(h in tokens or (len(h) > 3 and h in norm) for h in hints)


def _share(values: list[str], pattern: re.Pattern[str]) -> float:
    return sum(1 for v in values if pattern.match(v.strip())) / len(values) if values else 0.0


def _phone_like(value: str) -> bool:
    """Phone shapes need a separator or a leading "+" (bare digit runs are ids) and must
    not be dates."""
    v = value.strip()
    if not PHONE.match(v) or sum(c.isdigit() for c in v) < 7:
        return False
    if not (v.startswith("+") or any(sep in v for sep in " ()-.")):
        return False
    return parse_date(v) is None and not DATE_LIKE.match(v)


def detect_pii(header: str, values: Iterable[str | None]) -> PiiKind | None:
    sample = [v for v in values if v][:2000]
    if not sample:
        return None
    if _share(sample, EMAIL) >= 0.5:
        return PiiKind.EMAIL
    phones = [v for v in sample if _phone_like(v)]
    phone_share = len(phones) / len(sample)
    if phone_share >= (0.5 if _hint(header, PHONE_HINTS) else 0.9):
        return PiiKind.PHONE
    if _hint(header, ID_HINTS) and _share(sample, ID_NUMBER) >= 0.5:
        return PiiKind.NATIONAL_ID
    if _hint(header, NAME_HINTS):
        return PiiKind.PERSON_NAME
    return None


def mask_value(value: str | None, salt: str = "civiclens") -> str | None:
    """Stable pseudonym: same input → same output, irreversible without the salt."""
    if value is None or value == "":
        return value
    return "MASK-" + hashlib.sha256(f"{salt}:{value}".encode()).hexdigest()[:10]
