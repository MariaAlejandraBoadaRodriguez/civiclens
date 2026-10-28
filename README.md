# CivicLens

**Public-sector data analytics engine — from messy public files to decisions you can defend.**
Web app + public REST API that runs the full analytics lifecycle on government data: ingest → profile → guided cleaning → SQL modeling → machine learning → executive dashboard and report. UI in **English and Spanish**; input data in **English, French or Spanish**.

> 🚧 Status: **Phase 0 — scaffold.** See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the 25-day plan.

## Why
Public data arrives fragmented, multilingual and dirty, and executive reporting is often manual. CivicLens shows — step by step — how to turn it into reliable KPIs and decision support, and lets agencies repeat the same pipeline every month through an API.

## Stack
| Layer | Choice |
|---|---|
| Web | Next.js 14 · TypeScript · Tailwind · next-intl (EN/ES) · Vercel |
| API | FastAPI · Python 3.11 · Docker · Render |
| Analytics | DuckDB + Parquet · pandas |
| App data | PostgreSQL (Neon) |
| ML | scikit-learn · statsmodels · SHAP |
| CI/CD | GitHub Actions |

## Run locally
```bash
cp .env.example .env
docker compose up --build
# web → http://localhost:3000  (redirects to /en or /es)
# api → http://localhost:8000/health   docs → http://localhost:8000/docs
```

Without Docker:
```bash
# API
cd apps/api && python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
uvicorn app.main:app --reload

# Web
cd apps/web && npm install && npm run dev
```

## Repository layout
```
apps/web     Next.js app (UI, i18n catalogs in messages/en.json and messages/es.json)
apps/api     FastAPI service (analytics engine + public API)
data/seed    Frozen public datasets + dataset cards
docs/        Spec, roadmap, ADRs, glossary
scripts/     Tooling (i18n catalog check, seed loading)
```

## Quality gates (CI)
Ruff + pytest with coverage (API) · ESLint + typecheck + build (web) · EN/ES catalog parity · gitleaks secret scan · Docker build.

## Resumen en español
CivicLens es un motor de analítica para datos públicos: carga archivos en inglés, francés o español, enseña a limpiarlos, los modela en SQL, aplica modelos de machine learning explicables y genera el reporte ejecutivo. La interfaz está disponible en inglés y español, y todo el proceso se puede automatizar mediante una API para entidades públicas.

## Author
María Alejandra Boada Rodríguez — Data Analyst · Software Engineer

## License
MIT. Dataset licenses and attribution are listed in [`data/seed/README.md`](data/seed/README.md).
