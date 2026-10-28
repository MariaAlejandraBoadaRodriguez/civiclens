# Glossary EN ↔ ES

> Single source of truth for domain terms in the UI, educational content, reports and API messages.
> Spanish = neutral Latin American Spanish (ROADMAP A7). Use **exactly** these terms in `messages/es.json` and the backend ES catalogs; reviewers check new strings against this table.
> Canonical field names (`signed_date`, `amount_cad`, …) are never translated — only their labels.
> FR column shows how the term appears in French source data (Québec / Canada) to help header and value mapping; French is **data only**, never UI.

## Procurement domain

| # | English (UI) | Español (UI) | FR in source data | Canonical field / id | Notes |
|---|---|---|---|---|---|
| 1 | contract | contrato | contrat | `contract_id` | |
| 2 | public procurement | contratación pública | marchés publics / approvisionnement | — | |
| 3 | contracting entity / buyer | entidad contratante | organisme public / acheteur | `entity_id`, `entity_name` | "Entity" in UI, not "agency" |
| 4 | supplier | proveedor | fournisseur | `supplier_id`, `supplier_name` | Not "vendor" in UI (Canada data uses `vendor_name`) |
| 5 | contract value / amount | valor del contrato | montant du contrat / valeur | `amount_original` | |
| 6 | signed date | fecha de firma | date de signature | `signed_date` | |
| 7 | start date / end date | fecha de inicio / fecha de fin | date de début / date de fin | `start_date`, `end_date` | |
| 8 | award | adjudicación | adjudication | `award_id` | |
| 9 | award type / procurement method | modalidad de contratación | mode de sollicitation | `award_type` | |
| 10 | direct award | contratación directa | contrat de gré à gré | `award_type = direct` | |
| 11 | open (competitive) tender | licitación pública | appel d'offres public | `award_type = open` | |
| 12 | limited / selective tender | selección abreviada / invitación restringida | appel d'offres sur invitation | `award_type = limited` | |
| 13 | call for tenders / notice | aviso de convocatoria | avis d'appel d'offres | `tender_id` | |
| 14 | bidder / tenderer | oferente | soumissionnaire | `n_bidders` | |
| 15 | single-bidder contract | contrato con oferente único | soumissionnaire unique | red-flag rule | |
| 16 | amendment | modificación (adición) | modification / avenant | `amendment_value` | "adición" when the value increases |
| 17 | fiscal year | vigencia fiscal / año fiscal | exercice financier | `fiscal_year` | Colombia: calendar year; Canada/Québec: Apr–Mar |
| 18 | category (of spend) | categoría | catégorie / nature du contrat | `category_id` | |
| 19 | goods / services / construction works | bienes / servicios / obras | biens / services / travaux de construction | `category_type` | |
| 20 | threshold | umbral | seuil | — | "just under threshold" → "justo por debajo del umbral" |
| 21 | spend / total spend | gasto / gasto total | dépenses | KPI `total_spend` | |
| 22 | supplier concentration (HHI) | concentración de proveedores (IHH) | concentration des fournisseurs | KPI `hhi` | HHI = Herfindahl–Hirschman Index → Índice Herfindahl-Hirschman |
| 23 | jurisdiction | jurisdicción | juridiction / territoire | `jurisdiction` | |
| 24 | currency | moneda | devise | `currency` | ISO 4217 code always shown |
| 25 | exchange rate (FX) | tasa de cambio | taux de change | `fx_rate` | |
| 26 | proactive disclosure | divulgación proactiva | divulgation proactive | — | Canada dataset name |

## Data & analytics

| # | English (UI) | Español (UI) | Notes |
|---|---|---|---|
| 27 | dataset | conjunto de datos | Always "conjunto de datos" in ES UI, also in tight headings |
| 28 | sample data | datos de ejemplo | CTA: "Probar con datos de ejemplo" |
| 29 | upload | cargar (archivo) | Not "subir" in formal copy; button: "Cargar mi archivo" |
| 30 | ingest | ingesta | Lifecycle step 1 |
| 31 | profile (noun / verb) | perfil / perfilar | "Data profile" → "perfil de datos" |
| 32 | data quality score | puntaje de calidad de datos | |
| 33 | completeness / uniqueness / validity / consistency | completitud / unicidad / validez / consistencia | Quality dimensions |
| 34 | header mapping | mapeo de encabezados | |
| 35 | canonical schema / canonical field | esquema canónico / campo canónico | |
| 36 | data language | idioma de los datos | ≠ UI language ("idioma de la interfaz") |
| 37 | encoding / delimiter | codificación / delimitador | |
| 38 | null / missing value | valor nulo / valor faltante | |
| 39 | duplicate (row) / near-duplicate | (fila) duplicada / casi duplicada | |
| 40 | outlier | valor atípico | |
| 41 | data cleaning | limpieza de datos | |
| 42 | cleaning recipe | receta de limpieza | Versioned JSON — "receta", never "fórmula" |
| 43 | step (of a recipe) | paso | |
| 44 | replay (a recipe) | reaplicar / volver a aplicar | |
| 45 | issue (data issue) | problema (de datos) | Issue card → "tarjeta de problema" |
| 46 | before / after | antes / después | |
| 47 | personal data / PII | datos personales | "PII" only in technical docs |
| 48 | mask (data) | enmascarar | |
| 49 | lineage | linaje de datos | |
| 50 | star schema / fact table / dimension | esquema en estrella / tabla de hechos / dimensión | |
| 51 | query / guided query | consulta / consulta guiada | |
| 52 | KPI | KPI (indicador clave) | Keep "KPI" — widely used in LatAm public sector |
| 53 | dashboard | tablero | Not "dashboard" in ES UI; nav: "5 Tablero" |
| 54 | executive report | reporte ejecutivo | "reporte" (LatAm) rather than "informe" |
| 55 | filter | filtro | |
| 56 | forecast | pronóstico | |
| 57 | baseline (model) | línea base | |
| 58 | anomaly | anomalía | |
| 59 | red flag | alerta | Never "bandera roja"; never imply wrongdoing |
| 60 | leads, not accusations | pistas, no acusaciones | Mandatory model-card warning |
| 61 | mark as reviewed | marcar como revisado | |
| 62 | model card | ficha del modelo | |
| 63 | feature (ML) / feature contribution | variable / contribución de la variable | Not "característica" |
| 64 | training / test split | división entrenamiento / prueba | |
| 65 | segmentation / cluster | segmentación / segmento | |

## Product & API

| # | English (UI) | Español (UI) | Notes |
|---|---|---|---|
| 66 | API key | clave de API | |
| 67 | rate limit | límite de solicitudes | |
| 68 | job (async) | tarea | Status: queued/running/done/failed → en cola / en ejecución / terminada / fallida |
| 69 | endpoint | endpoint | Keep in English (technical) |
| 70 | Waking up the engine… | Encendiendo el motor… | Cold-start state |
| 71 | Learn more | Más información | |
| 72 | Apply / Skip for now | Aplicar / Omitir por ahora | |
| 73 | Export recipe as code | Exportar receta como código | |
| 74 | language switcher | selector de idioma | |

## Style rules (ES)

- Use **tú** (informal, respectful) consistently — the mockup tone is direct ("Carga tu archivo", "tú decides").
- Numbers: `1.234,56` with `es-CO`; always show the currency code (`COP`, `CAD`, `USD`).
- Dates: `28 de octubre de 2026` long form; `28/10/2026` short form (from `Intl`, never hand-built).
- Sentence case for headings and buttons ("Reporte ejecutivo", not "Reporte Ejecutivo").
- Keep code identifiers, SQL keywords and canonical field names in English inside `<code>`.
