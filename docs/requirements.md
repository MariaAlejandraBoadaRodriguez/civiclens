# CivicLens — Requirements (MVP freeze)

> Phase 1 deliverable. Source: `docs/SPEC.md` (what) and `docs/ROADMAP.md` (how/when; overrides the spec).
> Any scope change goes here first (MoSCoW), then into code (ROADMAP §8).

## 1. Personas

| ID | Persona | Language | Goal | Frustration today |
|---|---|---|---|---|
| **PS** | *Public servant* — analyst or manager in a ministry, city or agency | Spanish **or** English UI | Understand a contracts file, fix it, and present defensible numbers to leadership | Data arrives dirty, in several languages and formats; reporting is manual and slow |
| **AI** | *Agency integrator* — developer/analyst who automates a monthly report | Calls the API with `Accept-Language: en` or `es` | Push next month's file, replay the same cleaning recipe, get KPIs + red flags back | No stable, documented pipeline; every month starts from scratch |
| **RC** | *Recruiter / hiring manager* | English (mostly) or Spanish | Judge the owner's Data Analyst skills in < 5 minutes | Portfolios show notebooks, not an end-to-end product |

## 2. MoSCoW summary

| Priority | Scope |
|---|---|
| **Must** | Bilingual UI EN/ES · ingest CSV/XLSX/JSON with EN/FR/ES data · profile + quality score + PII scan · Cleaning Studio with recipes (replay + export pandas/SQL) · star schema + SQL Lab (read-only) + guided queries + KPI catalog · red-flag/anomaly model · spend forecast · executive dashboard + one-click report (HTML, EN/ES) · public REST API with API keys, rate limit and localized messages · 3 seed datasets selectable as sample data |
| **Should** | PDF report (HTML is the fallback) · Power BI/Tableau export · contract-category classifier · supplier segmentation · cross-jurisdiction comparison in one currency · case-study pages · Spanish explanations of all 12 guided queries |
| **Could** | Mobile SQL Lab editing (read-only list on mobile is Must-compatible) · dark theme · data dictionary page per dataset · `hreflang` sitemap |
| **Won't (MVP)** | End-user accounts (only admin via GitHub OAuth) · French UI (French *data* is supported) · S3 / long-term storage of uploads · real-time streaming · paid LLM calls · PDF table extraction · runtime machine translation |

Scope guard (ROADMAP §4): if late by Day 14, drop in order classifier → clustering → PDF → mobile SQL Lab → ES guided-query explanations. **The Spanish UI is never dropped.**

## 3. User stories

Format: *As a … I want … so that …* + Given/When/Then acceptance criteria. Each story maps to the phase/slice that delivers it (ROADMAP §3).

### Language & localization

#### US-01 · Choose the UI language — **Must** · PS, RC · Phase 3 (+6)
As a public servant, I want to switch the interface between English and Spanish so that I can work in the language I read best.
- **Given** I am on any page under `/en/...`, **when** I click `ES` in the header switcher, **then** I land on the same page under `/es/...` and every UI string (navigation, buttons, labels, explanations) is in Spanish.
- **Given** I switched to `ES`, **when** I close the browser and come back to `/`, **then** I am redirected to `/es` (cookie persistence).
- **Given** my browser sends `Accept-Language: es-CO` and I have no cookie, **when** I open `/`, **then** I am redirected to `/es`; with any non-`es*` language I get `/en`.
- **Given** any page, **then** `<html lang>` equals the active locale.

#### US-02 · Locale-aware numbers, dates and currency — **Must** · PS · Phase 3 (+6)
As a public servant, I want numbers and dates formatted the way my locale writes them so that I do not misread amounts.
- **Given** UI = EN, **when** a KPI of 1234.56 CAD is shown, **then** it reads `1,234.56` with the code `CAD` visible.
- **Given** UI = ES, **when** the same KPI is shown, **then** it reads `1.234,56` with the code `CAD` visible.
- **Given** any date, **then** it is formatted with `Intl.DateTimeFormat` for the active locale (`en-CA` / `es-CO`), never a hardcoded pattern.

#### US-03 · Data values are never translated — **Must** · PS, AI · Phase 5a
As a public servant, I want supplier names and contract descriptions shown exactly as in the source so that I can trace any number back to the original record.
- **Given** a French dataset and UI = ES, **when** I view the profile, **then** column *labels* are in Spanish but cell *values* (e.g. `Contrat de gré à gré`) are unchanged.
- **Given** any API response, **then** canonical field names are English (`signed_date`, `amount_cad`) regardless of `Accept-Language`.

#### US-04 · Localized API messages, stable machine fields — **Must** · AI · Phase 5e
As an agency integrator, I want to request human-readable messages in English or Spanish without my parser breaking so that the same integration serves both audiences.
- **Given** the same request sent with `Accept-Language: en` and `Accept-Language: es`, **when** I compare the responses, **then** machine fields (`issue_type`, `kpi_id`, `field`, numbers) are identical and only `title`/`message`/`explanation` differ.
- **Given** an error, **then** the body is RFC 7807 with a stable `type`/`code` and a localized `title`/`detail`, and the response carries `Content-Language`.
- **Given** an unsupported language (e.g. `fr`), **then** the API falls back to English and says so in `Content-Language: en`.

#### US-05 · Executive report in my language — **Must** · PS · Phase 5e / 6
As a manager, I want the executive report generated in the language of my UI so that I can forward it to leadership without rewriting it.
- **Given** UI = ES, **when** I click "Generar reporte ejecutivo", **then** the HTML report has Spanish headings, explanations and number formats; data values are untouched.
- **Given** the API call `GET /api/v1/reports/{id}?lang=en`, **then** the same report is returned in English.

### Ingest & profile (M1, M2)

#### US-06 · Try a sample dataset — **Must** · RC, PS · Phase 6 (data from Phase 1)
As a recruiter, I want to load a ready-made dataset with one click so that I can see the whole lifecycle without having a file.
- **Given** the landing page, **when** I click "Try with sample data" and pick *Colombia · SECOP II*, **then** the ingest & profile screen opens with that dataset already profiled in < 5 s (warm API).
- **Given** the landing page, **then** three sample cards are shown with language (`ES`, `EN / FR`, `FR`) and format badges.

#### US-07 · Upload a multilingual file — **Must** · PS · Phase 5a
As a public servant, I want to upload a CSV, XLSX or JSON file in English, French or Spanish so that I can analyse the data I actually receive.
- **Given** a valid file ≤ 50 MB, **when** I drop it on the dropzone, **then** format, encoding, delimiter (CSV), sheet (XLSX), header row and data language (% per column and overall) are detected and shown.
- **Given** a file > 50 MB or with an unsupported type, **then** the upload is rejected with a localized error before any processing.
- **Given** an uploaded file, **then** it is deleted automatically after 24 h and the UI says so.

#### US-08 · Map headers to the canonical schema — **Must** · PS · Phase 5a
As a public servant, I want Spanish and French headers mapped to one English schema so that datasets from different countries can be compared.
- **Given** headers `fecha_de_firma` or `date_signature`, **when** the file is profiled, **then** both map to `signed_date` with a confidence score.
- **Given** a mapping with confidence < 0.8, **then** it is flagged "check" and I can override it from a select; the override is saved in the recipe.

#### US-09 · Data quality score — **Must** · PS, RC · Phase 5a
As a manager, I want a single 0–100 data-quality score with its breakdown so that I know how much to trust the numbers.
- **Given** a profiled dataset, **then** I see the score and four bars: completeness, uniqueness, validity, consistency, each 0–100.
- **Given** the same file profiled twice, **then** the score is identical (deterministic).
- **Given** cleaning steps were applied, **then** the dashboard shows the score *before → after*.

#### US-10 · Personal-data warning — **Must** · PS · Phase 5a
As a public servant, I want columns containing personal data flagged and maskable so that I never leak PII in a chart, export or API response.
- **Given** a column with emails, phone numbers or national ID numbers, **when** the profile runs, **then** a PII alert lists the column and the detected kind.
- **Given** I click "Mask", **then** the values are replaced by a stable hash in every downstream view, export and API response.

### Cleaning Studio (M3)

#### US-11 · Understand and fix one issue at a time — **Must** · PS · Phase 5b + 6
As a public servant, I want each data issue explained with options and their impact so that I learn *why* I'm cleaning, not just *how*.
- **Given** a profiled dataset, **then** the issue list shows each detected issue with status Done / Now / To do and "x of N resolved".
- **Given** an issue card, **then** it shows category, "What we found", "Why it matters", radio options with hints, a Before/After preview and the impact on at least one KPI.
- **Given** I change the selected option, **then** the After panel, KPI impact and recipe preview update without a page reload.
- **Given** UI = ES, **then** every issue text (what/why/options/hints) comes from the ES catalog — no English fallback visible.

#### US-12 · Replay a cleaning recipe — **Must** · AI, PS · Phase 5b
As an agency integrator, I want my cleaning decisions saved as a versioned recipe so that next month's file is cleaned identically.
- **Given** a recipe and an input file, **when** I apply it twice, **then** the output Parquet has the same content hash both times.
- **Given** a new monthly file with the same schema, **when** I `POST /api/v1/datasets/{id}/recipes/apply`, **then** the same steps run and the response lists rows affected per step.

#### US-13 · Export the recipe as code — **Must** · RC, AI · Phase 5b
As a recruiter, I want to see the recipe as pandas and SQL code so that I can judge the engineering behind the UI.
- **Given** a recipe, **when** I choose the pandas / SQL / JSON tab, **then** I see generated code I can copy.
- **Given** the exported pandas script run on the raw file, **then** it reproduces the cleaned output (same hash).

#### US-14 · Unify currencies with a cited FX table — **Must** · PS · Phase 5b
As a manager, I want amounts converted to one currency using dated, sourced rates so that cross-country totals are meaningful and auditable.
- **Given** a dataset with COP, USD and CAD amounts, **when** I choose "Convert all to CAD", **then** each amount uses the rate of its signed date from `data/fx_rates.csv` and the UI shows the FX source.
- **Given** "Keep originals and add amount_cad", **then** no original value is overwritten.

### SQL Lab (M4)

#### US-15 · Guided business questions in SQL — **Must** · RC, PS · Phase 5c
As a recruiter, I want a library of guided queries with explanations so that I can see SQL skills (joins, CTEs, window functions) applied to real questions.
- **Given** the SQL Lab, **then** 12 guided questions are listed; clicking one loads its SQL into the editor with a "What this query teaches" explanation in the UI language.
- **Given** I click Run, **then** results appear with row count and execution time in ms; each guided query runs < 500 ms p95 locally.

#### US-16 · Safe read-only SQL — **Must** · AI, PS · Phase 5c
As the owner, I want the SQL sandbox to be read-only and bounded so that no visitor can damage data or the server.
- **Given** a query containing `INSERT`, `DROP`, `ATTACH`, `COPY`, `PRAGMA` or more than one statement, **when** it is submitted, **then** it is rejected with a localized error and nothing executes.
- **Given** a valid query that runs > 10 s or returns > 10,000 rows, **then** it is stopped / truncated and the UI says which limit applied.

#### US-17 · KPI catalog — **Must** · PS, AI · Phase 5c
As a manager, I want each KPI defined once (name, formula, SQL, owner) so that every department computes it the same way.
- **Given** `GET /api/v1/kpis/{dataset_id}`, **then** each KPI returns a stable `kpi_id`, value, unit/currency and a localized name + definition.

### ML Lab (M6)

#### US-18 · Red flags for human review — **Must** · PS · Phase 5d
As an auditor, I want contracts ranked by anomaly score with plain-language reasons so that I know where to look first — without accusing anyone.
- **Given** a cleaned dataset, **when** I run the red-flag model, **then** I see a ranked table (score, contract, reason chips such as "just under threshold", "single bidder", "fiscal-year-end spike") and a "Mark reviewed" action.
- **Given** the model card, **then** it states the business question, method, features and the warning "leads, not accusations" in the UI language.
- **Given** a fixed seed, **then** two runs return the same ranking.

#### US-19 · Spend forecast with an honest baseline — **Must** · PS · Phase 5d
As a manager, I want a monthly spend forecast compared against a naive baseline so that I know whether the model adds value.
- **Given** ≥ 24 months of history, **then** the forecast shows MAPE for the model and the seasonal-naive baseline; if the model does not beat it, the card says so.

#### US-20 · Classify contract categories from multilingual text — **Should** · PS · Phase 5d (stretch)
As an analyst, I want contract descriptions in EN/FR/ES classified into one category list so that spend by category is comparable.
- **Given** the classifier, **then** per-language precision/recall is shown on the model card.

#### US-21 · Supplier segmentation — **Should** · PS · Phase 5d (stretch)
As an analyst, I want suppliers grouped by spend, frequency and diversity so that I can describe the supplier base.
- **Given** the clusters, **then** each has a plain-language profile in the UI language.

### Dashboard, report & API (M5, M7)

#### US-22 · Executive dashboard — **Must** · PS, RC · Phase 6
As a manager, I want six KPI tiles, a monthly spend chart and filters so that I can brief leadership in minutes.
- **Given** a dataset, **then** the dashboard shows total spend, # contracts, average value, % direct award, HHI and data quality before → after.
- **Given** a 375 px wide screen, **then** tiles stack and no text is clipped in either language.

#### US-23 · Cross-jurisdiction comparison — **Should** · PS, RC · Phase 6
As a recruiter, I want Colombia, Canada and Québec compared in one currency so that I see the value of normalization.
- **Given** the comparison view, **then** spend per jurisdiction is shown in one chosen currency with the FX note.

#### US-24 · API keys for agencies — **Must** · AI · Phase 5e
As an agency integrator, I want a scoped, revocable API key so that my system can call CivicLens securely.
- **Given** the admin creates a key, **then** it is shown once and only its argon2 hash is stored.
- **Given** a request without a key / with a revoked key / with a key lacking scope, **then** the API answers 401 / 401 / 403 with a localized RFC 7807 body.
- **Given** more requests than the rate limit, **then** the API answers 429 with `Retry-After`.

#### US-25 · Monthly agency flow end-to-end — **Must** · AI · Phase 5e / 7
As an agency integrator, I want to upload a monthly file, apply my saved recipe and get KPIs + red flags in one scripted flow so that my report is fully automated.
- **Given** the `curl` quickstart (EN or ES), **when** I run it with a staging key, **then** it completes upload → recipe apply → KPIs → red flags without manual steps.
- **Given** a heavy operation, **then** the API returns a job id and `GET /api/v1/jobs/{id}` reports status until done.

#### US-26 · Cold-start feedback — **Must** · PS, RC · Phase 3 / 7
As a visitor, I want to know the engine is waking up so that I don't think the site is broken.
- **Given** the API takes > 3 s to respond to the first call, **then** a "Waking up the engine…" state is shown (translated) instead of a blank screen.

#### US-27 · Dataset licenses and attribution — **Must** · RC, PS · Phase 6 (data from Phase 1)
As a visitor, I want to see where each sample dataset comes from and its license so that the demo is legally and ethically sound.
- **Given** the footer link "Dataset licenses", **then** each seed dataset shows publisher, URL, license and date pulled, matching `data/seed/README.md`.

## 4. "Must" → phase traceability

| Story | Phase / slice |
|---|---|
| US-01, US-02 | 3 (foundation), 6 (screens) |
| US-03, US-07, US-08, US-09, US-10 | 5a |
| US-11, US-12, US-13, US-14 | 5b (+ 6 Cleaning screen) |
| US-15, US-16, US-17 | 5c (+ 6 SQL screen) |
| US-18, US-19 | 5d (+ 6 ML screen) |
| US-04, US-05, US-24, US-25 | 5e (+ 7 integration) |
| US-06, US-22, US-27 | 6 (seed data from 1) |
| US-26 | 3 (component), 7 (wiring) |

Every **Must** story is delivered by at least one phase; Phase 8 adds the automated tests that enforce the acceptance criteria (i18n diff, E2E in EN + ES, axe).

## 5. Non-functional requirements (MVP)

| ID | Requirement | Verified by |
|---|---|---|
| NFR-1 | WCAG 2.1 AA: axe 0 serious/critical on every page in both locales; contrast ≥ 4.5:1 | Phase 3 design pages, Phase 8 |
| NFR-2 | Dashboard readable at 375 px; Spanish strings ~30 % longer never clip | Phase 6 |
| NFR-3 | Uploads ≤ 50 MB, deleted after 24 h | Phase 5a, 9 |
| NFR-4 | Read-only SQL, 10 s timeout, 10,000-row cap | Phase 5c |
| NFR-5 | $0/month infrastructure | Phase 9 |
| NFR-6 | No hardcoded UI strings; EN/ES catalogs identical in keys (CI gate) | Phase 3+ |
| NFR-7 | No real personal data committed (seed data pseudonymised; see `data/seed/README.md`) | Phase 1 |
| NFR-8 | Backend coverage ≥ 80 % on `app/core`, ≥ 75 % overall | Phase 5, 8 |
