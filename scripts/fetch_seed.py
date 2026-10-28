"""Download the three seed datasets and write frozen Parquet samples to data/seed/.

Raw downloads go to data/raw/ (git-ignored). Samples are deterministic for a given
raw snapshot (fixed seed, stable sort before sampling).

Usage:
    pip install -r scripts/requirements.txt
    python scripts/fetch_seed.py            # all three
    python scripts/fetch_seed.py co ca qc   # a subset

Personal-data policy (see data/seed/README.md): columns that name or identify
individuals (legal representatives, supervisors, bank accounts, buyer names,
street addresses) are dropped; suppliers who are natural persons are pseudonymised
with a stable hash so supplier-level analysis still works.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
SEED = ROOT / "data" / "seed"
RANDOM_STATE = 42
TIMEOUT = 300

# --- A. Colombia · SECOP II -------------------------------------------------
SECOP_URL = "https://www.datos.gov.co/resource/jbjy-vk9h.csv"
SECOP_ROWS = 25_000
SECOP_COLUMNS = [
    "id_contrato",
    "referencia_del_contrato",
    "proceso_de_compra",
    "nombre_entidad",
    "nit_entidad",
    "codigo_entidad",
    "departamento",
    "ciudad",
    "orden",
    "sector",
    "rama",
    "entidad_centralizada",
    "estado_contrato",
    "codigo_de_categoria_principal",
    "descripcion_del_proceso",
    "objeto_del_contrato",
    "tipo_de_contrato",
    "modalidad_de_contratacion",
    "justificacion_modalidad_de",
    "fecha_de_firma",
    "fecha_de_inicio_del_contrato",
    "fecha_de_fin_del_contrato",
    "duraci_n_del_contrato",
    "tipodocproveedor",
    "documento_proveedor",
    "codigo_proveedor",
    "proveedor_adjudicado",
    "es_grupo",
    "es_pyme",
    "origen_de_los_recursos",
    "destino_gasto",
    "valor_del_contrato",
    "valor_pagado",
    "valor_facturado",
    "dias_adicionados",
    "espostconflicto",
    "ultima_actualizacion",
]
# Document types that identify a natural person (not a company).
SECOP_PERSON_DOC_TYPES = {
    "Cédula de Ciudadanía",
    "Cédula de Extranjería",
    "Pasaporte",
    "Tarjeta de Identidad",
    "Permiso por Protección Temporal",
    "Permiso especial de permanencia",
    "Registro Civil",
}

# --- B. Canada · Proactive publication of contracts -------------------------
CA_DATASTORE = "https://open.canada.ca/data/api/action/datastore_search"
CA_RESOURCE_ID = "fac950c0-00d5-4ec1-a4d3-9cbebf98a305"
CA_PERIODS = [f"2024-2025-Q{q}" for q in range(1, 5)]
CA_ROWS = 30_000
CA_DROP = ["_id", "buyer_name", "vendor_postal_code"]

# --- C. Québec · SEAO (OCDS JSON) -------------------------------------------
QC_BASE = (
    "https://www.donneesquebec.ca/recherche/dataset/d23b2e02-085d-43e5-9e6e-e1d558ebfdd5/resource"
)
QC_FILES = {
    "mensuel_20260701_20260731.json": "a336dd6c-cf8a-44f4-b3bb-5425c3274428",
    "mensuel_20260801_20260831.json": "b11b4088-f193-4ae8-83ec-d5e113bb164c",
    "mensuel_20260901_20260930.json": "b7ac3d06-bdc0-492d-8801-c7f650eba2ce",
}


def pseudonym(value: str, prefix: str) -> str:
    digest = hashlib.sha256(f"civiclens-seed:{value}".encode()).hexdigest()[:10]
    return f"{prefix}-{digest}"


def download(url: str, dest: Path, params: dict | None = None) -> Path:
    if dest.exists():
        print(f"  cached {dest.relative_to(ROOT)}")
        return dest
    print(f"  GET {url}")
    with requests.get(url, params=params, stream=True, timeout=TIMEOUT) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    return dest


def fetch_co() -> pd.DataFrame:
    raw = download(
        SECOP_URL,
        RAW / "secop_ii_contratos_2025.csv",
        params={
            "$select": ",".join(SECOP_COLUMNS),
            "$where": "fecha_de_firma >= '2025-01-01' AND fecha_de_firma < '2026-01-01'",
            "$order": ":id",
            "$limit": SECOP_ROWS,
        },
    )
    df = pd.read_csv(raw, dtype=str, keep_default_na=False)
    person = df["tipodocproveedor"].isin(SECOP_PERSON_DOC_TYPES)
    df.loc[person, "proveedor_adjudicado"] = df.loc[person, "documento_proveedor"].map(
        lambda v: pseudonym(v, "PERSONA NATURAL")
    )
    df.loc[person, "documento_proveedor"] = df.loc[person, "documento_proveedor"].map(
        lambda v: pseudonym(v, "DOC")
    )
    df.loc[person, "codigo_proveedor"] = df.loc[person, "codigo_proveedor"].map(
        lambda v: pseudonym(v, "PROV")
    )
    print(f"  pseudonymised {int(person.sum())} natural-person suppliers")
    return df


def fetch_ca() -> pd.DataFrame:
    raw = RAW / "contracts_ca_2024-2025.jsonl"
    if not raw.exists():
        # The full CSV (≈640 MB) is served from a blob host; the CKAN datastore API
        # returns the same records and lets us filter one fiscal year server-side.
        offset, page = 0, 32_000
        with raw.open("w", encoding="utf-8") as f:
            while True:
                print(f"  datastore offset={offset}")
                r = requests.get(
                    CA_DATASTORE,
                    params={
                        "resource_id": CA_RESOURCE_ID,
                        "filters": json.dumps({"reporting_period": CA_PERIODS}),
                        "sort": "_id",
                        "limit": page,
                        "offset": offset,
                    },
                    timeout=TIMEOUT,
                )
                r.raise_for_status()
                records = r.json()["result"]["records"]
                for rec in records:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                if len(records) < page:
                    break
                offset += page
    else:
        print(f"  cached {raw.relative_to(ROOT)}")
    df = pd.read_json(raw, lines=True, dtype=False)
    df = df.drop(columns=[c for c in CA_DROP if c in df.columns])
    df = df.sort_values("reference_number", kind="stable")
    n = min(CA_ROWS, len(df))
    df = df.sample(n=n, random_state=RANDOM_STATE).sort_values("reference_number")
    return df.astype("string")


def flatten_release(rel: dict) -> list[dict]:
    parties = {p.get("id"): p for p in rel.get("parties", [])}
    tender = rel.get("tender", {})
    items = tender.get("items") or [{}]
    item = items[0]
    awards = {a.get("id"): a for a in rel.get("awards", [])}
    buyer = rel.get("buyer", {})
    buyer_party = parties.get(buyer.get("id"), {})
    rows = []
    for c in rel.get("contracts", []):
        award = awards.get(c.get("awardID"), {})
        suppliers = award.get("suppliers") or [{}]
        sup = suppliers[0]
        sup_party = parties.get(sup.get("id"), {})
        rows.append(
            {
                "ocid": rel.get("ocid"),
                "release_id": rel.get("id"),
                "release_date": rel.get("date"),
                "release_tag": ",".join(rel.get("tag", [])),
                "acheteur_nom": buyer.get("name"),
                "acheteur_id": buyer.get("id"),
                "acheteur_ville": buyer_party.get("address", {}).get("locality"),
                "acheteur_region": buyer_party.get("address", {}).get("region"),
                "organisme_municipal": buyer_party.get("details", {}).get("municipal"),
                "avis_numero": tender.get("id"),
                "avis_titre": tender.get("title"),
                "avis_statut": tender.get("status"),
                "mode_sollicitation": tender.get("procurementMethod"),
                "mode_sollicitation_detail": tender.get("procurementMethodDetails"),
                "justification": tender.get("procurementMethodRationale"),
                "categorie_principale": tender.get("mainProcurementCategory"),
                "categories_additionnelles": ",".join(
                    tender.get("additionalProcurementCategories") or []
                ),
                "unspsc_code": item.get("classification", {}).get("id"),
                "unspsc_description": item.get("classification", {}).get("description"),
                "nature_description": item.get("description"),
                "nombre_soumissionnaires": tender.get("numberOfTenderers"),
                "fournisseur_nom": sup.get("name"),
                "fournisseur_id": sup.get("id"),
                "fournisseur_neq": sup_party.get("details", {}).get("neq"),
                "fournisseur_ville": sup_party.get("address", {}).get("locality"),
                "fournisseur_region": sup_party.get("address", {}).get("region"),
                "fournisseur_pays": sup_party.get("address", {}).get("countryName"),
                "nombre_fournisseurs": len(award.get("suppliers") or []),
                "adjudication_id": award.get("id"),
                "adjudication_date": award.get("date"),
                "adjudication_montant": award.get("value", {}).get("amount"),
                "contrat_id": c.get("id"),
                "contrat_statut": c.get("status"),
                "contrat_montant": c.get("value", {}).get("amount"),
                "devise": c.get("value", {}).get("currency"),
                "date_signature": c.get("dateSigned"),
                "url_avis": (tender.get("documents") or [{}])[0].get("url"),
            }
        )
    return rows


def fetch_qc() -> pd.DataFrame:
    rows: list[dict] = []
    for name, resource_id in QC_FILES.items():
        path = download(f"{QC_BASE}/{resource_id}/download/{name}", RAW / f"seao_{name}")
        data = json.loads(path.read_text(encoding="utf-8"))
        for rel in data["releases"]:
            rows.extend(flatten_release(rel))
    df = pd.DataFrame(rows)
    # Keep the latest release per contract (contractUpdate supersedes contract).
    df = df.sort_values(["ocid", "contrat_id", "release_date"], kind="stable")
    df = df.drop_duplicates(["ocid", "contrat_id"], keep="last").reset_index(drop=True)
    return df.astype("string")


JOBS = {
    "co": ("secop_co.parquet", fetch_co),
    "ca": ("contracts_ca.parquet", fetch_ca),
    "qc": ("contracts_qc.parquet", fetch_qc),
}


def main(argv: list[str]) -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    SEED.mkdir(parents=True, exist_ok=True)
    for key in argv or list(JOBS):
        out, fn = JOBS[key]
        print(f"[{key}] {out}")
        df = fn()
        df.to_parquet(SEED / out, index=False, compression="zstd")
        print(f"  wrote {len(df):,} rows × {df.shape[1]} cols → data/seed/{out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
