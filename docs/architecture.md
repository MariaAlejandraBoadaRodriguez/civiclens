# CivicLens — Architecture

> Phase 4 deliverable. Decisions and trade-offs live in [`docs/adr/`](adr/README.md); the API contract is [`openapi.yaml`](../openapi.yaml); requirements in [`requirements.md`](requirements.md).

## 1. System context

```mermaid
flowchart LR
  subgraph Users
    PS["Public servant / recruiter<br/>browser · EN or ES"]
    AG["Agency system<br/>API key · Accept-Language"]
    AD["Admin<br/>GitHub OAuth"]
  end

  subgraph Vercel
    WEB["Next.js web app<br/>/en · /es · next-intl"]
    MSG[["UI catalogs<br/>en.json · es.json"]]
  end

  subgraph Render["Render (Docker)"]
    API["FastAPI /api/v1<br/>auth · rate limit · locale"]
    I18N[["Domain catalogs<br/>issues · KPIs · model cards · errors"]]
    CORE["Core engine<br/>ingest · profile · cleaning · SQL · ML · reports"]
    DUCK[("DuckDB<br/>read-only SQL")]
    FILES[["Parquet<br/>seed + 24 h uploads"]]
  end

  NEON[("Neon Postgres<br/>keys · datasets · recipes · jobs · audit")]

  PS --> WEB
  AD --> WEB
  WEB --- MSG
  WEB -->|"REST + Accept-Language"| API
  AG -->|"X-API-Key + Accept-Language"| API
  API --> I18N
  API --> CORE
  CORE --> DUCK
  DUCK --> FILES
  CORE --> FILES
  API --> NEON
```

| Component | Tech | Responsibility | ADR |
|---|---|---|---|
| Web | Next.js 14, next-intl, Tailwind, Radix | 6 screens + admin, UI strings, number/date formatting | 0001, 0007 |
| API | FastAPI, Pydantic v2 | `/api/v1` contract, auth, rate limit, language negotiation, jobs | 0004, 0007 |
| Core engine | pandas/Polars, DuckDB, scikit-learn, statsmodels | Pure functions: parse, profile, clean, model, report | 0002, 0006 |
| Analytics store | Parquet + DuckDB | Raw/staged/clean data and star schema | 0002 |
| App DB | Postgres (Neon), SQLAlchemy 2, Alembic | Keys, dataset metadata, recipes, jobs, audit | 0003 |
| Hosting | Vercel · Render · Neon | $0 | 0005 |

## 2. Data flow and lineage

```mermaid
flowchart LR
  F["Upload or seed file<br/>CSV · XLSX · JSON"] --> R["raw.parquet<br/>strings, as-is"]
  R -->|"detect format, encoding,<br/>data language; map headers"| S["staged.parquet<br/>canonical schema, typed"]
  S -->|"profile + quality score + PII scan"| P[("datasets.profile_json")]
  S -->|"recipe steps (pure functions)"| C["clean.parquet"]
  C -->|"star-schema builder"| SS["fact_contract + dim_*"]
  SS --> Q["SQL Lab / KPIs"]
  SS --> M["ML: red flags, forecast"]
  Q --> REP["Dashboard + executive report"]
  M --> REP
```

Every arrow is recorded: recipes in `recipes`, runs in `jobs`, user decisions in `audit_log`. Same input + same recipe → same `clean.parquet` hash.

## 3. App database (migration 001)

```mermaid
erDiagram
  api_keys ||--o{ jobs : "submits"
  datasets ||--o{ jobs : "processed by"
  datasets |o--o{ recipes : "built on"

  api_keys {
    uuid id PK
    string name
    string prefix UK "public lookup prefix"
    string hash "argon2"
    json scopes
    timestamptz created_at
    timestamptz last_used_at
    timestamptz revoked_at
  }
  datasets {
    uuid id PK
    string slug UK "seed only, e.g. secop_co"
    string name
    string source "seed | upload | api"
    string format "csv | xlsx | json | parquet"
    string data_lang "en | fr | es | mixed | unknown"
    string status "uploaded ... expired"
    bigint rows
    int columns
    int quality_score "0-100"
    text raw_path
    text staged_path
    json profile_json
    timestamptz created_at
    timestamptz expires_at "NULL for seed"
  }
  recipes {
    uuid id PK
    string name UK "unique with version"
    int version
    uuid dataset_id FK "SET NULL"
    json steps_json
    timestamptz created_at
  }
  jobs {
    uuid id PK
    string type
    string status "queued | running | succeeded | failed"
    uuid dataset_id FK "CASCADE"
    uuid api_key_id FK "SET NULL"
    json input_json
    json result_json
    string error_code "localized at read time"
    timestamptz created_at
    timestamptz started_at
    timestamptz finished_at
  }
  audit_log {
    bigint id PK
    string actor
    string action
    string target
    json details_json
    timestamptz at
  }
```

Commands (from `apps/api`): `alembic upgrade head` · `alembic downgrade base` · `alembic -x url=<url> upgrade head`. `tests/test_migrations.py` runs upgrade → model/migration diff → downgrade on SQLite, and on Postgres 16 in CI.

## 4. Analytics star schema (DuckDB, built in slice 5c)

```mermaid
erDiagram
  fact_contract }o--|| dim_entity : entity_id
  fact_contract }o--|| dim_supplier : supplier_id
  fact_contract }o--|| dim_date : date_id
  fact_contract }o--|| dim_category : category_id
  fact_contract }o--|| dim_currency : currency

  fact_contract {
    string contract_id PK
    string entity_id FK
    string supplier_id FK
    int date_id FK "yyyymmdd of signed_date"
    string category_id FK
    decimal amount_original
    string currency FK "ISO 4217"
    decimal amount_cad
    string award_type "direct | open | limited | other"
    int n_bidders
  }
  dim_entity {
    string entity_id PK
    string entity_name "as in source"
    string jurisdiction "CO | CA | QC"
    string region
  }
  dim_supplier {
    string supplier_id PK
    string supplier_name "as in source; pseudonymised for natural persons"
    string country
    date first_seen
  }
  dim_date {
    int date_id PK
    date date
    int year
    int month
    int fiscal_year "per jurisdiction"
    int days_to_fy_end
  }
  dim_category {
    string category_id PK
    string code "UNSPSC / GSIN"
    string label_en
    string label_es
    string label_source "original language value"
  }
  dim_currency {
    string currency PK
    string name
  }
```

## 5. Canonical schema and seed mapping

Field names are English and never translated (ADR-0006, ADR-0007). Labels are translated in the catalogs.

| Canonical field | Colombia · SECOP II | Canada · federal | Québec · SEAO |
|---|---|---|---|
| `contract_id` | `id_contrato` | `reference_number` | `ocid` + `contrat_id` |
| `entity_name` | `nombre_entidad` | `owner_org_title` | `acheteur_nom` |
| `supplier_name` | `proveedor_adjudicado` | `vendor_name` | `fournisseur_nom` |
| `signed_date` | `fecha_de_firma` | `contract_date` | `date_signature` |
| `start_date` / `end_date` | `fecha_de_inicio_del_contrato` / `fecha_de_fin_del_contrato` | `contract_period_start` / `delivery_date` | — |
| `amount_original` | `valor_del_contrato` | `contract_value` | `contrat_montant` |
| `currency` | — (COP implied) | — (CAD implied) | `devise` |
| `award_type` | `modalidad_de_contratacion` | `solicitation_procedure` | `mode_sollicitation` |
| `n_bidders` | — | `number_of_bids` | `nombre_soumissionnaires` |
| `category_code` | `codigo_de_categoria_principal` | `commodity_code` | `unspsc_code` |
| `description` | `objeto_del_contrato` | `description_en` / `description_fr` | `avis_titre` |

## 6. Agency flow (US-25)

```mermaid
sequenceDiagram
  autonumber
  participant A as Agency system
  participant API as FastAPI /api/v1
  participant DB as Postgres
  participant E as Core engine + DuckDB
  A->>API: POST /datasets (file, X-API-Key, Accept-Language: es)
  API->>DB: insert dataset + job (queued)
  API-->>A: 202 {dataset, job}
  API->>E: background: ingest + profile
  E->>DB: job succeeded, profile_json
  A->>API: POST /datasets/{id}/recipes/apply {recipe_id}
  API-->>A: 202 {job}
  A->>API: GET /jobs/{job_id}
  API-->>A: 200 {status: succeeded}
  A->>API: GET /kpis/{id}
  API-->>A: 200 kpi_id + value (stable) · name + definition (es)
  A->>API: POST /models/red_flags/run
  API-->>A: 202 {job} → result: ranked leads + reasons (es)
```

## 7. Cross-cutting concerns

| Concern | Approach |
|---|---|
| i18n | ADR-0007: UI catalogs in web, domain catalogs in API, `Accept-Language` → `Content-Language`, stable machine fields |
| Security | API keys (argon2 + prefix, scopes, revocation), admin via GitHub OAuth, read-only DuckDB + statement guard, upload type sniffing + 50 MB cap, CORS allowlist, PII masking |
| Errors | RFC 7807 with stable `code`; DB stores codes only |
| Jobs | Postgres rows + FastAPI background tasks; idempotent, re-runnable |
| Retention | Uploads `expires_at = now() + 24 h`, purge job; seed data permanent |
| Observability | `/health`; JSON logs with request id + locale; Sentry (Phase 10) |
| Accessibility | WCAG 2.1 AA; axe in CI on both locales |

## 8. Endpoint ↔ story map

| Endpoint | Stories |
|---|---|
| `GET /health` | US-26 |
| `GET /api/v1/datasets` | US-06, US-27 |
| `POST /api/v1/datasets` | US-07, US-25 |
| `GET /api/v1/datasets/{id}` | US-07 |
| `GET /api/v1/datasets/{id}/profile` | US-03, US-08, US-09, US-10 |
| `GET /api/v1/datasets/{id}/issues` | US-04, US-11, US-14 |
| `POST /api/v1/datasets/{id}/recipes/apply` | US-12, US-14, US-25 |
| `POST /api/v1/recipes` · `GET /api/v1/recipes/{id}` | US-12 |
| `GET /api/v1/recipes/{id}/export` | US-13 |
| `POST /api/v1/query` | US-15, US-16 |
| `GET /api/v1/guided-queries` | US-15 |
| `GET /api/v1/kpis/{id}` | US-17, US-22, US-23, US-25 |
| `POST /api/v1/models/{type}/run` | US-18, US-19, US-20, US-21, US-25 |
| `GET /api/v1/jobs/{id}` | US-25 |
| `GET /api/v1/reports/{id}` | US-05 |
| `GET/POST /api/v1/keys` · `DELETE /api/v1/keys/{id}` | US-24 |

Enforced by Spectral (`operation-user-stories` rule) and `apps/api/tests/test_openapi_contract.py`.
