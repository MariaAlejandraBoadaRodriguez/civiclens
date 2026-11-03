"""Map EN / FR / ES source headers to the canonical schema (ADR-0006).

Exact dictionary hits score 0.97–1.0; otherwise a fuzzy string similarity is used.
Each canonical field is assigned at most once (best match wins). Confidence < 0.8 is
flagged for the user to check. Canonical names are English and never translated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import StrEnum

from app.core.ingest.locale_parse import strip_accents

CHECK_THRESHOLD = 0.8
MIN_FUZZY = 0.72  # below this a fuzzy match is only offered as a candidate
FUZZY_WEIGHT = 0.85


class FieldType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    DATE = "date"
    CATEGORY = "category"
    CURRENCY = "currency"


@dataclass(frozen=True)
class CanonicalField:
    name: str
    type: FieldType
    synonyms: frozenset[str] = field(default_factory=frozenset)


def _f(name: str, type_: FieldType, *synonyms: str) -> CanonicalField:
    return CanonicalField(name, type_, frozenset(normalize_header(s) for s in (name, *synonyms)))


def normalize_header(header: object) -> str:
    text = strip_accents(str(header)).lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


CANONICAL_FIELDS: tuple[CanonicalField, ...] = (
    _f(
        "contract_id",
        FieldType.STRING,
        "id_contrato",
        "numero_contrato",
        "numero_del_contrato",
        "reference_number",
        "contract_number",
        "contrat_id",
        "numero_contrat",
        "no_contrat",
    ),
    _f(
        "entity_id",
        FieldType.STRING,
        "nit_entidad",
        "codigo_entidad_en_secop",
        "owner_org",
        "acheteur_id",
        "entity_code",
        "code_organisme",
        "id_organisme",
    ),
    _f(
        "entity_name",
        FieldType.CATEGORY,
        "nombre_entidad",
        "entidad",
        "entidad_contratante",
        "owner_org_title",
        "acheteur_nom",
        "organisme",
        "organisme_public",
        "department",
        "entity",
        "buyer",
        "ministere",
    ),
    _f(
        "supplier_id",
        FieldType.STRING,
        "documento_proveedor",
        "nit_proveedor",
        "nit_del_proveedor",
        "fournisseur_id",
        "fournisseur_neq",
        "neq",
        "vendor_id",
        "supplier_number",
        "vendor_number",
    ),
    _f(
        "supplier_name",
        FieldType.STRING,
        "proveedor_adjudicado",
        "proveedor",
        "nombre_proveedor",
        "razon_social",
        "contratista",
        "vendor_name",
        "vendor",
        "supplier",
        "fournisseur_nom",
        "fournisseur",
        "nom_fournisseur",
        "adjudicataire",
    ),
    _f(
        "signed_date",
        FieldType.DATE,
        "fecha_de_firma",
        "fecha_firma",
        "fecha_de_firma_del_contrato",
        "contract_date",
        "date_signed",
        "signature_date",
        "date_signature",
        "date_de_signature",
        "date_de_la_signature",
    ),
    _f(
        "start_date",
        FieldType.DATE,
        "fecha_de_inicio_del_contrato",
        "fecha_inicio",
        "fecha_de_inicio",
        "contract_period_start",
        "date_debut",
        "date_de_debut",
    ),
    _f(
        "end_date",
        FieldType.DATE,
        "fecha_de_fin_del_contrato",
        "fecha_fin",
        "fecha_de_terminacion",
        "delivery_date",
        "contract_end_date",
        "date_fin",
        "date_de_fin",
    ),
    _f(
        "amount_original",
        FieldType.NUMBER,
        "valor_del_contrato",
        "valor_contrato",
        "valor",
        "valor_total",
        "monto",
        "monto_adjudicado",
        "valor_adjudicado",
        "importe",
        "contract_value",
        "amount",
        "value",
        "total_value",
        "contrat_montant",
        "montant",
        "montant_du_contrat",
        "montant_contrat",
        "valeur_du_contrat",
        "valeur",
    ),
    _f(
        "currency",
        FieldType.CURRENCY,
        "moneda",
        "divisa",
        "tipo_de_moneda",
        "devise",
        "monnaie",
        "currency_code",
    ),
    _f(
        "award_type",
        FieldType.CATEGORY,
        "modalidad_de_contratacion",
        "modalidad",
        "modalidad_de_seleccion",
        "solicitation_procedure",
        "procurement_method",
        "mode_sollicitation",
        "mode_de_sollicitation",
        "mode_adjudication",
        "procedure",
    ),
    _f(
        "n_bidders",
        FieldType.INTEGER,
        "number_of_bids",
        "numero_de_oferentes",
        "numero_ofertas",
        "nombre_soumissionnaires",
        "nombre_de_soumissionnaires",
        "bids",
        "tenderers",
    ),
    _f(
        "category_code",
        FieldType.CATEGORY,
        "codigo_de_categoria_principal",
        "codigo_unspsc",
        "commodity_code",
        "unspsc_code",
        "unspsc",
        "gsin",
        "code_unspsc",
    ),
    _f(
        "description",
        FieldType.STRING,
        "objeto_del_contrato",
        "objeto",
        "descripcion_del_proceso",
        "descripcion",
        "description_en",
        "description_fr",
        "avis_titre",
        "objet",
        "objet_du_contrat",
        "titre",
        "nature_description",
    ),
    _f(
        "contract_type",
        FieldType.CATEGORY,
        "tipo_de_contrato",
        "tipo_contrato",
        "commodity_type",
        "categorie_principale",
        "nature_du_contrat",
        "type_de_contrat",
    ),
    _f(
        "status",
        FieldType.CATEGORY,
        "estado_contrato",
        "estado_del_contrato",
        "estado",
        "contrat_statut",
        "statut",
        "contract_status",
    ),
    _f(
        "region",
        FieldType.CATEGORY,
        "departamento",
        "acheteur_region",
        "province",
        "region_administrative",
    ),
    _f(
        "city", FieldType.CATEGORY, "ciudad", "municipio", "acheteur_ville", "ville", "municipalite"
    ),
)
BY_NAME = {f.name: f for f in CANONICAL_FIELDS}


@dataclass(frozen=True)
class HeaderMatch:
    source_header: str
    canonical_field: str | None
    confidence: float
    candidates: tuple[str, ...]  # best alternatives, for the override select

    @property
    def needs_check(self) -> bool:
        return self.canonical_field is not None and self.confidence < CHECK_THRESHOLD


def _score(norm: str, target: CanonicalField) -> float:
    if norm == target.name:
        return 1.0
    if norm in target.synonyms:
        return 0.97
    # Fuzzy similarity is capped at 0.85 so only dictionary hits are "sure"; a fuzzy
    # match needs ratio ≥ 0.85 to be assigned and is flagged "check" below ratio 0.94.
    return FUZZY_WEIGHT * max(SequenceMatcher(None, norm, s).ratio() for s in target.synonyms)


def score_header(header: str) -> list[tuple[float, str]]:
    """All canonical fields ranked for one header. Bilingual headers ("Contract value /
    Valeur du contrat") are scored per part and the best part wins."""
    parts = [p for p in re.split(r"[/|]", str(header)) if p.strip()] or [str(header)]
    norms = {normalize_header(p) for p in parts} | {normalize_header(header)}
    ranked = [(round(max(_score(n, f) for n in norms if n), 2), f.name) for f in CANONICAL_FIELDS]
    return sorted(ranked, reverse=True)


def map_headers(headers: list[str]) -> list[HeaderMatch]:
    """Greedy one-to-one assignment: highest-confidence pairs first."""
    ranked = {h: score_header(h) for h in headers}
    pairs = sorted(
        ((score, h, name) for h, scores in ranked.items() for score, name in scores),
        key=lambda t: (-t[0], headers.index(t[1]), t[2]),
    )
    assigned: dict[str, tuple[str, float]] = {}
    used: set[str] = set()
    for score, header, name in pairs:
        if score < MIN_FUZZY:
            break
        if header in assigned or name in used:
            continue
        assigned[header] = (name, score)
        used.add(name)
    result = []
    for h in headers:
        name, score = assigned.get(h, (None, 0.0))
        candidates = tuple(n for s, n in ranked[h][:3] if s >= 0.45)
        result.append(HeaderMatch(h, name, score, candidates))
    return result
