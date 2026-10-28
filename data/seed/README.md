# Seed datasets

Three frozen samples of public procurement data — one per jurisdiction — used as the "Try with sample data" clients.
All three are **open-licensed**; attribution below must stay visible in the app (footer → "Dataset licenses").

| File | Jurisdiction | Data language | Source format | Rows × cols | Status |
|---|---|---|---|---|---|
| `secop_co.parquet` | Colombia (SECOP II) | ES | CSV (Socrata API) | 25,000 × 37 | ✅ pulled 2026-10-28 |
| `contracts_ca.parquet` | Canada (federal) | EN/FR bilingual | CSV / CKAN datastore JSON | 30,000 × 41 | ✅ pulled 2026-10-28 |
| `contracts_qc.parquet` | Québec (SEAO) | FR | JSON (OCDS releases) | 46,826 × 37 | ✅ pulled 2026-10-28 |

**Reproduce:** `pip install -r scripts/requirements.txt && python scripts/fetch_seed.py`.
Raw downloads land in `data/raw/` (git-ignored, ~380 MB). Samples are deterministic for a given raw snapshot (`random_state=42`).
All columns are stored as strings, **exactly as published** (no cleaning, no type casting): cleaning is the product's job.

## Personal-data policy (applies to all three)

Public procurement records are published openly, but this repo must not redistribute data that identifies individuals.
`scripts/fetch_seed.py` therefore:

- **drops** columns that name or identify people who are not the contracting party: legal representatives, supervisors, payment/spending officers, bank accounts (SECOP — simply not selected), `buyer_name` and `vendor_postal_code` (Canada), street addresses (Québec — only city/region kept);
- **pseudonymises** suppliers who are natural persons in SECOP (`tipodocproveedor` = cédula, passport, etc.): `proveedor_adjudicado` → `PERSONA NATURAL-<hash>`, `documento_proveedor` → `DOC-<hash>`, `codigo_proveedor` → `PROV-<hash>`. The hash is a stable SHA-256 prefix, so supplier-level KPIs (HHI, top suppliers) still work.

Residual: Canada `vendor_name` and Québec `fournisseur_nom` may occasionally be a sole proprietor's name (≈3 % of Canadian vendors are written "Last, First"). These are business names as registered and published by the governments; they are kept unchanged. PII detection demos (emails, phone numbers) use synthetic values injected by `scripts/make_dirty.py` (Phase 5a), never real ones.

---

## A · Colombia — SECOP II, Contratos Electrónicos

| Field | Value |
|---|---|
| Publisher | Agencia Nacional de Contratación Pública — Colombia Compra Eficiente |
| Portal page | https://www.datos.gov.co/Gastos-Gubernamentales/SECOP-II-Contratos-Electr-nicos/jbjy-vk9h |
| Endpoint used | `https://www.datos.gov.co/resource/jbjy-vk9h.csv` (Socrata SODA) |
| License | **Creative Commons Attribution-ShareAlike 4.0 (CC BY-SA 4.0)** — https://creativecommons.org/licenses/by-sa/4.0/ |
| Date pulled | 2026-10-28 |
| Selection | `fecha_de_firma` in calendar year 2025, first 25,000 records in dataset order (`$order=:id`) |
| Rows / columns | 25,000 / 37 (of 100+ published; person-level columns not selected) |
| Data language | Spanish (headers and values) |
| Currency | COP (implicit — no currency column) |

**Columns:** `id_contrato`, `referencia_del_contrato`, `proceso_de_compra`, `nombre_entidad`, `nit_entidad`, `codigo_entidad`, `departamento`, `ciudad`, `orden`, `sector`, `rama`, `entidad_centralizada`, `estado_contrato`, `codigo_de_categoria_principal` (UNSPSC), `descripcion_del_proceso`, `objeto_del_contrato`, `tipo_de_contrato`, `modalidad_de_contratacion`, `justificacion_modalidad_de`, `fecha_de_firma`, `fecha_de_inicio_del_contrato`, `fecha_de_fin_del_contrato`, `duraci_n_del_contrato`, `tipodocproveedor`, `documento_proveedor`\*, `codigo_proveedor`\*, `proveedor_adjudicado`\*, `es_grupo`, `es_pyme`, `origen_de_los_recursos`, `destino_gasto`, `valor_del_contrato`, `valor_pagado`, `valor_facturado`, `dias_adicionados`, `espostconflicto`, `ultima_actualizacion`. (\* pseudonymised for natural persons.)

**Known issues (as published):** ~85 % of contracts are *prestación de servicios* to natural persons (hence pseudonymised); ~75 % `Contratación directa`; durations as free text (`30 Dia(s)`, `3 Mes(es)`); category variants with/without "(con ofertas)"; empty strings instead of nulls; timestamps without time zone.
**Attribution text (display):** "SECOP II – Contratos Electrónicos, Colombia Compra Eficiente, CC BY-SA 4.0. Sample, pseudonymised."
**ShareAlike note:** the Parquet sample is a derivative; it is redistributed under CC BY-SA 4.0 (the repository's MIT license covers code only).

## B · Canada — Proactive Publication of Contracts (federal)

| Field | Value |
|---|---|
| Publisher | Treasury Board of Canada Secretariat (aggregated from all federal departments) |
| Portal page | https://open.canada.ca/data/en/dataset/d8f85d91-7dec-4fd1-8055-483b77225d8b |
| Resource | "Contracts over $10,000" — resource id `fac950c0-00d5-4ec1-a4d3-9cbebf98a305` |
| Endpoint used | CKAN `datastore_search` (same records as `contracts.csv`), filter `reporting_period` ∈ 2024-2025-Q1…Q4 |
| License | **Open Government Licence – Canada 2.0** — https://open.canada.ca/en/open-government-licence-canada |
| Date pulled | 2026-10-28 (resource last modified 2026-10-27) |
| Selection | All 87,091 records of fiscal year 2024-2025 → random sample of 30,000 (`random_state=42`) |
| Rows / columns | 30,000 / 41 |
| Data language | Bilingual: English headers; paired `*_en` / `*_fr` value columns; `owner_org_title` as "English \| Français" |
| Currency | CAD |

**Columns:** `reference_number`, `procurement_id`, `vendor_name`, `contract_date`, `economic_object_code`, `description_en`, `description_fr`, `contract_period_start`, `delivery_date`, `contract_value`, `original_value`, `amendment_value`, `comments_en`, `comments_fr`, `additional_comments_en`, `additional_comments_fr`, `agreement_type_code`, `trade_agreement`, `land_claims`, `commodity_type`, `commodity_code`, `country_of_vendor`, `solicitation_procedure`, `limited_tendering_reason`, `trade_agreement_exceptions`, `indigenous_business`, `indigenous_business_excluding_psib`, `intellectual_property`, `potential_commercial_exploitation`, `former_public_servant`, `contracting_entity`, `standing_offer_number`, `instrument_type`, `ministers_office`, `number_of_bids`, `article_6_exceptions`, `award_criteria`, `socioeconomic_indicator`, `reporting_period`, `owner_org`, `owner_org_title`. Code lists: data dictionary https://open.canada.ca/data/recombinant-published-dictionary/contracts.

**Known issues (as published):** `number_of_bids` null in ~26 %; coded fields (`solicitation_procedure` = TC/TN/OB/ST/AC) need the dictionary; contract dates back to 1999 for long-running amended contracts; vendor names in mixed case/accents ("Last, First" for some individuals); amendments reported as separate rows.
**Attribution text (display):** "Contains information licensed under the Open Government Licence – Canada."
**Format note:** the spec lists this dataset as XLSX. The portal publishes CSV only (the data dictionary is XLSX). The XLSX ingest path will be exercised with an XLSX export produced by `scripts/make_dirty.py`.

## C · Québec — Système électronique d'appel d'offres (SEAO)

| Field | Value |
|---|---|
| Publisher | Secrétariat du Conseil du trésor du Québec |
| Portal page | https://www.donneesquebec.ca/recherche/dataset/systeme-electronique-dappel-doffres-seao |
| Files used | `mensuel_20260701_20260731.json`, `mensuel_20260801_20260831.json`, `mensuel_20260901_20260930.json` (OCDS 1.1 release packages) |
| License | **Creative Commons Attribution 4.0 (CC BY 4.0)** — https://www.donneesquebec.ca/licence/#cc-by |
| Date pulled | 2026-10-28 |
| Selection | Every contract in every release of the 3 monthly files, flattened to one row per (`ocid`, `contrat_id`), keeping the latest release |
| Rows / columns | 46,826 / 37 |
| Data language | French (values); column names are French renderings of OCDS paths (see below) |
| Currency | CAD |

**Columns (OCDS path):** `ocid`, `release_id`, `release_date`, `release_tag`, `acheteur_nom`/`acheteur_id` (buyer), `acheteur_ville`, `acheteur_region`, `organisme_municipal`, `avis_numero` (tender.id), `avis_titre`, `avis_statut`, `mode_sollicitation` (procurementMethod), `mode_sollicitation_detail`, `justification` (procurementMethodRationale), `categorie_principale`, `categories_additionnelles`, `unspsc_code`, `unspsc_description`, `nature_description`, `nombre_soumissionnaires` (numberOfTenderers), `fournisseur_nom`, `fournisseur_id`, `fournisseur_neq` (Québec enterprise number), `fournisseur_ville`, `fournisseur_region`, `fournisseur_pays`, `nombre_fournisseurs`, `adjudication_id`, `adjudication_date`, `adjudication_montant`, `contrat_id`, `contrat_statut`, `contrat_montant`, `devise`, `date_signature`, `url_avis`.

**Known issues (as published):** placeholder dates (`0001-01-01T00:00:00-04:57`); old contracts re-published in recent releases (signed dates back to 2005); dates with time-zone offsets; `fournisseur_neq` missing for ~9 %; only the first supplier / first item kept when an award has several (`nombre_fournisseurs` tells how many); free-text rationale mixing article numbers and prose.
**Attribution text (display):** "Données du SEAO, Secrétariat du Conseil du trésor, Données Québec, CC BY 4.0."
**Format note:** the original JSON is nested (OCDS). The flat Parquet is what the demo uses; the nested JSON path of the ingest module is tested with a raw monthly file in Phase 5a.

---

## Demo ("dirty") versions — what "Try with sample data" loads

The app does not show the seed Parquet directly. On first use the API runs
`app/core/seed/dirty.py` (also available as `python scripts/make_dirty.py`, output in the
git-ignored `data/demo/`) to write each seed in its jurisdiction's original format with
**documented, deterministic** data-quality issues (fixed seed `20261028`; same input → byte-identical file).
This is what the ingest screen profiles and what the Cleaning Studio fixes.

| Seed | Demo file | Rows | Injected issues (counts are exact) |
|---|---|---|---|
| `secop_co` | `secop_co.csv` — `;` delimiter, Windows-1252 | 25,400 | 412 USD + 88 CAD amounts in a new `moneda` column · 15 outliers (×1000) · 3,000 amounts in EN notation (rest ES `1.234,56`) · `fecha_de_firma` as dd/mm/yyyy (7,500) and mm/dd/yyyy (1,500) · 2,250 coded nulls (`N/A`, `-`, `sin dato`, `No Definido`, empty) · 2,000 case/accent/spacing name variants · 300 exact + 100 near duplicates · fuzzy header `Modalidad de Contratación (SECOP)` · synthetic `email_contacto` / `telefono_contacto` (example.org, `+57 300 555 ….`) |
| `contracts_ca` | `contracts_ca.xlsx` — title row, bilingual headers | 10,130 | 200 USD amounts (new `currency` column) · 1,500 amounts in FR notation `1 234,56` · 1,000 dates as mm/dd/yyyy · 400 coded nulls in `number_of_bids` · 300 vendor-name variants · 100 exact + 30 near duplicates · 4 bilingual headers (`Contract value / Valeur du contrat`, …) · 2 title rows above the header |
| `contracts_qc` | `contracts_qc.json` — nested `acheteur.*` / `fournisseur.*` | 20,200 | 6,000 amounts as FR-formatted strings · 3,000 dates as dd/mm/yyyy, the rest ISO with time-zone offsets · 600 coded nulls (`non disponible`, `N/D`, `-`) · 800 buyer-name variants · 6 outliers · 200 exact duplicates |

Canada and Québec demo files are deterministic subsets (10,000 / 20,000 seed rows) to keep XLSX
reading fast; the seed Parquet files above are unchanged.

## FX table — `data/fx_rates.csv`

Used by the Cleaning Studio to convert currencies with the rate of each contract's signed month
(ROADMAP A5: static, dated, cited). Columns: `month`, `currency` (COP, USD, CAD), `cad_per_unit`, `source`.
Rebuild with `python scripts/fetch_fx.py`.

| Pair | Source | Status |
|---|---|---|
| COP per USD | TRM, Superintendencia Financiera de Colombia (datos.gov.co `32sa-8pi3`, CC BY-SA 4.0) — monthly mean of daily values, 2015-01 → 2026-10 | ✅ official |
| CAD per USD | Bank of Canada `FXMUSDCAD` monthly average | ⚠️ **approximate annual averages** — the Bank of Canada, StatCan, ECB and FRED hosts are blocked from the build sandbox |

**To replace the approximation:** download https://www.bankofcanada.ca/valet/observations/FXMUSDCAD/csv
and run `python scripts/fetch_fx.py --boc-csv FXMUSDCAD.csv`. Rows built from the approximation say so in their `source` column,
and the Cleaning Studio shows that source under the currency KPI.

## If a download breaks later

- **Canada full CSV** (`contracts.csv`, ~640 MB) is served from `opencanada.blob.core.windows.net`, which the Claude cloud sandbox cannot reach; the script uses the CKAN datastore API instead. To audit against the original file, download
  https://open.canada.ca/data/dataset/d8f85d91-7dec-4fd1-8055-483b77225d8b/resource/fac950c0-00d5-4ec1-a4d3-9cbebf98a305/download/contracts.csv
  manually into `data/raw/` (not needed to run the app).
- SEAO monthly files rotate; if a resource id disappears, pick the three latest `mensuel_*.json` on the portal page and update `QC_FILES` in `scripts/fetch_seed.py`.
