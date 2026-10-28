# CivicLens — Public-Data Analytics Engine (Spec for Devin)

> Working name; owner may rename. UI, code, docs, commits: **English only**. Input data may be **EN / FR / ES**.

## 0. Purpose
Portfolio-grade web app + public API that runs the full data analytics lifecycle on public-sector data:
**Ingest → Profile → Clean (guided, educational) → Model (SQL) → Analyze → Predict (ML) → Report/Dashboard → API**.
Audience: (a) hiring managers for Data Analyst / Analytics Engineer roles, (b) public servants who need to understand their own data and make decisions, (c) government agencies consuming it via API.

Owner background to reflect: 9 yrs automating executive reporting for government programs, consolidating 15–20 heterogeneous sources, standardizing KPIs across departments.

## 1. Team & workflow
- **Alejandra** (owner): decides scope, reviews PRs, approves milestones.
- **Devin**: implements one milestone per session, opens a PR, writes tests + short PR summary.
- **Claude**: reviews spec/PRs, data-quality logic, ML choices, copy.
- Rules: small PRs; every milestone must pass its acceptance criteria and run locally with `docker compose up`; no milestone may depend on a paid service.

## 2. Tech stack (keep it simple)
| Layer | Choice |
|---|---|
| Frontend | Next.js 14 (App Router) + TypeScript + Tailwind + Recharts; deploy on Vercel |
| Backend/API | Python 3.11 + FastAPI (OpenAPI docs at `/docs`); Docker |
| Analytics engine | DuckDB (in-process SQL over Parquet) + pandas/Polars |
| App DB | PostgreSQL (users, API keys, recipes, run logs). Neon free tier in prod |
| ML | scikit-learn, statsmodels; SHAP for explanations |
| Language | `langdetect` for detection; built-in EN/FR/ES header & value dictionaries; optional LLM translation behind a feature flag (off by default) |
| Storage | Seed datasets committed as Parquet. User uploads: local volume, auto-deleted after 24h (no S3 in MVP) |
| CI | GitHub Actions: lint, pytest, frontend build |
| Backend hosting | Render or Fly.io (Docker) |

## 3. Seed datasets (3 demo "clients")
Theme: **public procurement / contracts** across 3 jurisdictions → enables cross-country comparison.
| # | Jurisdiction | Language | Format | Suggested source (Devin: verify URL + license, record in dataset card) |
|---|---|---|---|---|
| A | Colombia | ES | CSV | datos.gov.co — SECOP II contracts |
| B | Canada (federal) | EN/FR bilingual | XLSX | open.canada.ca — Proactive disclosure of contracts |
| C | Québec | FR | JSON | Données Québec / SEAO contract data |

Requirements:
- Store a **frozen snapshot** (~10k–50k rows each) under `data/seed/` + `data/seed/README.md` dataset cards (source, license, date pulled, row count, columns).
- `scripts/make_dirty.py`: deterministically (fixed seed) injects documented issues so the cleaning tutorial is reproducible: exact + near duplicates, mixed currencies (COP/CAD/USD), mixed number locales (`1.234,56` vs `1,234.56`), mixed date formats (`dd/mm/yyyy`, `mm/dd/yyyy`, ISO), time zones, accents/case variants in entity names, nulls coded as `N/A`, `-`, `sin dato`, `non disponible`, outliers, bilingual headers.
- Each seed dataset is selectable in the UI as "Try with sample data".

## 4. Features by module

### M1 — Ingest
- Upload CSV, XLSX, JSON (PDF tables = stretch goal). Max 50 MB.
- Auto-detect: encoding, delimiter, sheet, header row, language (per column + overall).
- Header normalization: map EN/FR/ES headers to a canonical schema (e.g. `fecha_firma` / `date de signature` → `signed_date`); show mapping; user can override.
- Convert to Parquet; store raw + staged versions (lineage).

### M2 — Profile
- Per column: type inferred, null %, distinct, min/max, top values, pattern, locale guess.
- Dataset-level **Data Quality Score** (0–100) with breakdown: completeness, uniqueness, validity, consistency.
- PII scan (names, emails, ID numbers, phones) → flag + offer masking.

### M3 — Cleaning Studio (educational core)
Each detected issue = an **Issue Card**:
- What: "1,284 duplicate rows (3.2%) — 1,102 exact, 182 near-duplicates (same supplier+amount+date ±1 day)".
- Why it matters: 1–2 plain sentences (e.g. "Duplicates inflate total spend KPIs").
- Options (radio): e.g. keep first / keep last / keep all and flag.
- **Before/after preview** + impact on KPIs (e.g. total spend changes by −4.1%).
- Learn more: short tooltip explaining the concept.
Issue types: duplicates, missing values (drop/impute/flag), currency unification (choose target: COP/CAD/USD; FX table with date + source shown), number locale, date/time normalization (+ time zone to UTC/local), text normalization (trim, case, accents, entity name fuzzy match), outliers (IQR/z-score: flag, cap, keep), type casting, category standardization (ES/FR/EN values → EN canonical labels).
- Every decision is saved to a **Cleaning Recipe** (JSON, versioned) → replayable on new data via UI or API.
- **Export recipe as code**: generated pandas script + equivalent SQL. (Shows the engineering.)
- Cleaning log: who/when/what/rows affected.

### M4 — SQL Lab
- Build a **star schema** from cleaned data: `fact_contract`, `dim_entity`, `dim_supplier`, `dim_date`, `dim_category`, `dim_currency`. Show ER diagram.
- SQL editor (DuckDB, **read-only**, timeout 10s, row limit 10k) with result grid + quick chart.
- **Guided queries** library (~12), each with business question + SQL + explanation, e.g.: top suppliers by spend; spend concentration (HHI); direct award vs competitive share; month-over-month spend; contracts signed near fiscal year end; supplier with contracts across many entities; window functions; CTEs; cohort of new suppliers.
- KPI definitions catalog (name, formula, SQL, owner) — mirrors KPI standardization experience.

### M5 — Analytics & Dashboard
- Executive dashboard per dataset + **cross-jurisdiction comparison** (normalized to one currency).
- KPIs: total spend, # contracts, avg value, % direct award, supplier concentration, YoY growth, data quality score.
- Filters: jurisdiction, entity, period, category, supplier.
- **One-click executive report** (PDF/HTML): KPIs, charts, top findings, data quality notes, recipe applied. (Mirrors owner's reporting automation work.)
- Export star schema as Parquet/CSV for **Power BI / Tableau** + include a short guide in `docs/`.

### M6 — ML Lab (decision support, human-in-the-loop)
Each model page: business question, features used, train/test split, metrics, explanation (SHAP/feature importance), limitations, **model card**.
1. **Anomaly / red-flag detection** — Isolation Forest + rule-based red flags (split contracts, end-of-year spikes, single-bidder, amount just under thresholds). Output: ranked list for human review, never an accusation.
2. **Spend forecasting** — monthly spend per entity; baseline (seasonal naive) vs SARIMA/gradient boosting; MAPE shown.
3. **Contract category classification** from multilingual descriptions — TF-IDF (char n-grams) + Logistic Regression; per-language metrics.
4. **Supplier segmentation** — KMeans on spend/frequency/diversity features; cluster profiles in plain English.
- Models retrainable on the user's cleaned data; saved with version + metrics.

### M7 — Public API
- FastAPI, versioned `/api/v1`, OpenAPI docs, API keys (hashed), rate limiting, async jobs for heavy work.
- Endpoints (minimum):
  - `POST /datasets` upload · `GET /datasets/{id}/profile`
  - `GET /datasets/{id}/issues` · `POST /datasets/{id}/recipes/apply` (recipe JSON)
  - `POST /query` (read-only SQL) · `GET /kpis/{dataset_id}`
  - `POST /models/{type}/run` · `GET /jobs/{id}`
  - `GET /reports/{dataset_id}` (PDF/HTML)
- Example clients: `curl` + Python snippet in README. Use case: agency pushes monthly file → same recipe applied → KPIs + red flags returned.

### M8 — Landing / portfolio layer
- Landing page: problem, lifecycle diagram, "Try sample data", link to API docs, GitHub, owner's portfolio.
- "Case study" page per seed dataset: question → cleaning decisions → SQL → insight → model → recommendation.

## 5. Non-functional
- Security: read-only SQL sandbox, upload validation, size limits, CORS allowlist, secrets via env vars, PII masking.
- Uploads deleted after 24h; seed data permanent.
- Accessibility: keyboard nav, color-blind-safe palette, WCAG AA contrast.
- Tests: pytest for cleaning ops, locale parsing (EN/FR/ES numbers/dates), recipe replay, API; ≥70% backend coverage.
- Docs: README (setup, architecture diagram, screenshots), `docs/architecture.md`, `docs/data-dictionary.md`, ADRs for key decisions.

## 6. Milestones (one Devin session each)
| # | Deliverable | Acceptance criteria |
|---|---|---|
| 0 | Repo scaffold, docker compose, CI, empty Next.js + FastAPI | `docker compose up` serves both; CI green |
| 1 | Seed datasets + dataset cards + `make_dirty.py` | 3 Parquet files load; injected issues documented |
| 2 | Ingest + Profile (M1, M2) | Upload all 3 formats; headers mapped; quality score shown |
| 3 | Cleaning Studio + recipes + code export (M3) | All issue types work on seed A; recipe replays identically |
| 4 | SQL Lab + star schema + guided queries (M4) | 12 guided queries run; read-only enforced |
| 5 | Dashboard + executive report + BI export (M5) | Cross-jurisdiction view in one currency; PDF generated |
| 6 | ML Lab (M6) | 4 models with metrics + model cards |
| 7 | Public API + keys + rate limit (M7) | End-to-end API flow tested |
| 8 | Landing, case studies, deploy (M8) | Live URLs: Vercel frontend + Docker backend + Neon DB |

## 7. Job-requirement coverage (keep README section)
| Skill employers list | Where shown |
|---|---|
| SQL (joins, CTEs, window functions) | M4 guided queries |
| Python (pandas, ETL) | M1–M3, generated code |
| Data cleaning / data quality | M2–M3 |
| Data modeling (star schema) | M4 |
| KPI definition | M4 catalog, M5 |
| BI / dashboards (Power BI, Tableau) | M5 + export |
| Statistics, forecasting, ML | M6 |
| Stakeholder reporting | M5 executive report |
| APIs / automation | M7 |
| Cloud, Docker, CI/CD, testing | §2, §5 |
| Data privacy / governance | PII scan, lineage, recipe logs |

## 8. Out of scope (MVP)
Auth for end users beyond API keys, S3, real-time streaming, paid LLM calls by default, PDF table extraction (stretch).
