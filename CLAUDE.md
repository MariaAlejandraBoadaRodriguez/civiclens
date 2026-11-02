# CivicLens — instructions for Claude

Read `docs/ROADMAP.md` (how/when, overrides the spec) and `docs/SPEC.md` (what) before any work.
Approved UI mockups: https://claude.ai/artifact/1FACLDLoSx3hTmETMXnVr9 — build screens to match them.

## Working agreement
- One session = one phase or slice from ROADMAP §4. The owner names it ("Day N, phase X").
- Work on a branch `phase-<n>-<short-name>`, open a PR to `main`, never push to `main` directly.
- PR description: what changed, how to verify (in `/en` and `/es`), DoD checklist from the roadmap.
- Talk to the owner (Alejandra) in **Spanish**; everything committed is in **English** (except `messages/es.json`, Spanish YAML catalogs and `*.es.md` docs).

### Quality gates (owner's rule)
- **Every change has tests.** A fix comes with the test that would have caught it; a feature with
  unit tests and, when it touches a journey, an E2E step in `/en` and `/es`.
- **A PR is ready only when every CI job is green**, including
  `Stack · API in 512 MB — full flow + E2E (EN/ES)` (Docker image with `--memory=512m`, the full
  flow on the three seeds, Playwright journeys failing on any console error, no OOM kill) and
  `Web · lint + typecheck + build` (with the Vitest unit tests).
- **Never ask the owner to merge a red PR**, and never mark it ready for review while red: fix it,
  or say exactly what blocks it. Never skip, disable or loosen a test to get green.
- Run the checks locally before pushing (see Commands). Changes to memory-heavy code (ingest,
  cleaning, models) are measured with `scripts/flow_check.py` against the Docker image.
- **Deploys are gated:** Render deploys `main` only after its checks pass
  (`autoDeployTrigger: checksPass`); Vercel promotes to production only after the
  "Vercel - civiclens: ci-passed" Deployment Check; `.github/workflows/post-deploy.yml` smoke-tests
  production and opens an issue with rollback steps if it fails.

## Conventions
- Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`).
- **i18n:** no hardcoded UI text. Every string goes through `t()` and is added to BOTH `apps/web/messages/en.json` and `es.json`. Run `python scripts/check_i18n.py`.
- UI language (EN/ES) ≠ data language (EN/FR/ES). Never translate data values. Canonical field names are always English.
- API: machine fields stay English and stable; human-readable text localized via `Accept-Language`.
- Fonts are self-hosted via `@fontsource` (no `next/font/google`: the build must work offline).

## Commands
```bash
# API
cd apps/api && pip install -e ".[dev]" && ruff check . && ruff format --check . && pytest   # TEST_DATABASE_URL=postgresql+psycopg://... also runs migrations on Postgres
# Migrations (apps/api): alembic upgrade head
# OpenAPI: npx @stoplight/spectral-cli@6.14.2 lint openapi.yaml
# Web
cd apps/web && npm ci && npm run lint && npm run typecheck && npm test && npm run build
# E2E (stack running: API on :8000, `next start` on :3000): cd apps/web && npm run test:e2e
# Full flow against an API (any 5xx/OOM fails): python scripts/make_dirty.py --out /tmp/demo &&
#   python scripts/flow_check.py --base http://127.0.0.1:8000 --mode full --files /tmp/demo
# i18n
python scripts/check_i18n.py
```

## Suggested environment setup script (claude.ai/code)
```bash
cd apps/api && pip install -e ".[dev]" && cd ../web && npm ci
```
