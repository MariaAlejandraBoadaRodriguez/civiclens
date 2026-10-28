"""The three seed ("Try with sample data") datasets. Display names live in the i18n
catalogs (``datasets.<slug>.name``); everything here is language-neutral."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL, "https://github.com/MariaAlejandraBoadaRodriguez/civiclens"
)


@dataclass(frozen=True)
class Seed:
    slug: str
    parquet: str
    format: str
    jurisdiction: str
    license: str
    source_url: str

    @property
    def id(self) -> uuid.UUID:
        """Stable id so links like /datasets/<id> survive restarts and redeploys."""
        return uuid.uuid5(_NAMESPACE, f"seed:{self.slug}")


SEEDS: dict[str, Seed] = {
    s.slug: s
    for s in (
        Seed(
            "secop_co",
            "secop_co.parquet",
            "csv",
            "CO",
            "CC BY-SA 4.0",
            "https://www.datos.gov.co/Gastos-Gubernamentales/SECOP-II-Contratos-Electr-nicos/jbjy-vk9h",
        ),
        Seed(
            "contracts_ca",
            "contracts_ca.parquet",
            "xlsx",
            "CA",
            "OGL-Canada 2.0",
            "https://open.canada.ca/data/en/dataset/d8f85d91-7dec-4fd1-8055-483b77225d8b",
        ),
        Seed(
            "contracts_qc",
            "contracts_qc.parquet",
            "json",
            "QC",
            "CC BY 4.0",
            "https://www.donneesquebec.ca/recherche/dataset/systeme-electronique-dappel-doffres-seao",
        ),
    )
}
SEEDS_BY_ID = {s.id: s for s in SEEDS.values()}
