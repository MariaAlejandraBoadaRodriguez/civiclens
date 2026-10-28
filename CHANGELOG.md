# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/) and [Semantic Versioning](https://semver.org/).

## [Unreleased]
### Added
- Phase 0: monorepo scaffold (Next.js 14 + next-intl EN/ES, FastAPI), Docker Compose, CI, repo templates.
- Phase 1: `docs/requirements.md` (27 user stories, MoSCoW, traceability), `docs/glossary.md` (74 EN↔ES terms), seed datasets (`data/seed/*.parquet`) with dataset cards and `scripts/fetch_seed.py`.
- Phase 3: design tokens (CSS variables + Tailwind), component library, `/en/design` + `/es/design`, locale formatting helpers, ESLint rule against hardcoded JSX strings, axe CI job, placeholder check in `check_i18n.py`.

- Slice 5b: cleaning engine — 15 pure operations, 12 issue detectors with options, Before/After previews and KPI impact, versioned recipe JSON with validation and deterministic replay (output SHA-256), export to a self-contained pandas script (reproduces the output exactly) and DuckDB SQL, FX table (`data/fx_rates.csv`, `scripts/fetch_fx.py`), `/api/v1/datasets/{id}/issues`, `/api/v1/recipes` (save/version, preview, export), apply jobs with audit log, EN/ES issue catalogs, Cleaning Studio screen with live option → After / KPI / recipe updates.
- Slice 5a: ingest (CSV/XLSX/JSON/Parquet detection, encoding, delimiter, header row, nested JSON), EN/FR/ES data-language detection, header mapping to the canonical schema, locale-aware number/date/null parsing, raw + staged Parquet, profiler + row-level Data Quality Score, PII scan, `scripts/make_dirty.py` demo data, `/api/v1/datasets` + `/api/v1/jobs` with localized RFC 7807 errors, backend EN/ES catalogs, Ingest & profile screen (`/[locale]/datasets/[id]`) with upload.
- Phase 4: ADRs 0001–0007 (`docs/adr/`), `docs/architecture.md` (system, lineage, ERDs, agency sequence), `openapi.yaml` v0 + Spectral CI job, SQLAlchemy 2 models + Alembic migration 001 (tested on SQLite and Postgres 16), Postgres in docker compose.