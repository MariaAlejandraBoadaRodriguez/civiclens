# ADR-0001 · Monorepo with Next.js web + FastAPI API

- **Status:** Accepted · 2026-10-28
- **Deciders:** Alejandra (owner), Claude (implementer)

## Context
CivicLens has two deployables — a bilingual web app and a public analytics API — built by one developer plus an AI agent, in 25 working days. The analytics work (parsing, cleaning, SQL, ML) is Python-native; the UI must be server-rendered, localized (`/en`, `/es`) and previewed per PR.

## Decision
- One GitHub repository: `apps/web` (Next.js 14 App Router, TypeScript, Tailwind, next-intl) and `apps/api` (Python 3.11, FastAPI, Pydantic v2). Shared contract = `openapi.yaml` at the root.
- No JS/Python monorepo tool (Nx, Turborepo, Pants): two independent package managers (`npm`, `pip`) and one CI workflow with a job per app.
- FastAPI because pandas/Polars, DuckDB, scikit-learn and statsmodels are Python, and FastAPI generates the OpenAPI docs agencies need.

## Consequences
- ✅ One PR can change API + UI + contract atomically; recruiters read one history.
- ✅ Each app keeps its native tooling; CI jobs run in parallel.
- ⚠️ Types cross the language boundary only through OpenAPI; drift is prevented by generating the TS client (`openapi-typescript`, Phase 6) and Schemathesis (Phase 8).
- ⚠️ Two dependency ecosystems to keep patched (Dependabot covers both).

## Alternatives considered
- **Next.js API routes only (TypeScript backend):** one language, but no first-class DuckDB/sklearn/statsmodels story — rejected.
- **Django:** batteries included, but slower for async jobs and less natural for an OpenAPI-first public API.
