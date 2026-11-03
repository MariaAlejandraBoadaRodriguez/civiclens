# Production-readiness checklist (ROADMAP §5) — v1.0.0

Status on 2026-11-03. ✅ done, with the evidence that proves it; ⏳ open, with the reason and the
owner action. Evidence is a test, a CI job (`.github/workflows/ci.yml`) or a document; every CI
job runs on every PR and gates the deploy.

## Security

| Item | Status | Evidence |
|---|---|---|
| API keys stored as argon2 hashes, scoped, revocable; shown once at creation | ✅ | `tests/test_public_api.py::test_key_is_shown_once_and_only_its_argon2_hash_is_stored`, `…_are_401_everywhere`; E2E "admin signs in, issues a scoped key, … then it is revoked" (EN, ES) |
| Admin console behind GitHub OAuth with allowlisted account | ✅ code · ⏳ OAuth app | `lib/admin/access.ts` + `tests/unit/adminAccess.test.ts`; E2E admin journey. **Owner:** create the GitHub OAuth App and set the variables (see the release PR) |
| SQL Lab: read-only connection, statement allowlist, timeout, row cap, injection suite green | ✅ | `app/core/sql/guard.py`, `engine.py`; `tests/test_sql.py` (malicious statements, timeout, 10,000-row cap, locked configuration, concurrency) |
| Uploads: type sniffing, 50 MB cap, no macro execution, 24 h TTL purge job | ✅ | `app/core/ingest/detect.py` (magic bytes, OLE/macro containers rejected), `UPLOAD_MAX_MB=50` → 413, `purge_expired` on each upload; `tests/test_ingest_detect.py`, `tests/test_datasets_api.py` |
| PII scan + masking before data is shown or exported | ✅ | `app/core/profile/pii.py`, `mask_columns` op; `tests/test_profile.py`, `tests/test_cleaning_ops.py` |
| CORS allowlist = production web domain only; security headers (CSP, HSTS, X-Frame-Options) | ✅ | `render.yaml` `ALLOWED_ORIGINS` = production origin only (+ Vercel previews by regex); startup refuses non-https origins in production (`tests/test_observability.py::test_production_fails_fast…`); web `security-headers.mjs` + `tests/unit/securityHeaders.test.ts`; API headers `tests/test_observability.py`; E2E runs with the CSP and fails on any console error |
| Rate limits on all public endpoints; 429 tested | ✅ | `app/api/security.py`; `tests/test_public_api.py::test_rate_limit_answers_429…`, heavy limit, per-key bucket, proxy-safe client IP |
| gitleaks, pip-audit, npm audit clean; Dependabot on | ✅ gitleaks, pip-audit, Dependabot · ⏳ npm audit | Jobs "Security · secret scan" and "Security · pip-audit"; `.github/dependabot.yml`. `npm audit` reports advisories against **Next.js 14** (Image Optimizer, Server Actions, rewrites, i18n Pages Router). CivicLens uses none of `next/image`, Server Actions, rewrites or the Pages Router, so the reachable surface is small, but the fix is Next 15+ (a major upgrade, outside the Dependabot policy). Planned as a follow-up PR, not ticked. |

## Environment variables

| Item | Status | Evidence |
|---|---|---|
| `.env.example` complete; no secret in repo history | ✅ | `.env.example` lists every API and web variable; gitleaks scans the full history on every PR |
| Separate staging / production values | ⏳ | Production and Vercel previews only; there is no separate staging service on the free tier. Preview deployments use the production API. |
| App fails fast at startup if a required variable is missing | ✅ API · ✅ web (degrades) | API: `Settings._production_is_configured`, tested. Web: `/admin` lists the missing variables instead of crashing (`adminConfig`, tested) |

## Data & backups

| Item | Status | Evidence |
|---|---|---|
| Neon point-in-time restore; restore drill | ⏳ n/a | Production uses SQLite on the container disk: uploads, recipes and jobs are ephemeral by design (24 h), and the seeds are rebuilt from the image. Neon is the documented option for persistence (`docs/runbook.md` §3, §5). |
| Seed Parquet + dataset cards versioned in repo | ✅ | `data/seed/*.parquet`, `data/seed/README.md`; FX table `data/fx_rates.csv` (dated, cited) |
| Alembic migrations reversible (`downgrade` tested) | ✅ | `tests/test_migrations.py::test_downgrade_to_base` on SQLite and on Postgres 16 (CI service) |

## Internationalization

| Item | Status | Evidence |
|---|---|---|
| EN and ES catalogs complete (FE + BE), CI check green | ✅ | Job "i18n · EN/ES catalogs match" (`scripts/check_i18n.py`) |
| `<html lang>` correct per locale; `hreflang` alternates | ✅ | `app/[locale]/layout.tsx` (`lang`, `alternates.languages`); the axe job checks `lang` on 20 pages |
| Numbers, dates and currency per locale; currency code always visible | ✅ | `lib/format.ts` (`en-CA`, `es-CO`) + unit tests; API `app/core/reports/format.py` |
| Executive report and API errors in both languages | ✅ | `tests/test_public_api.py::test_report_in_the_requested_language`, `…pdf_in_the_requested_language…`; same-request EN/ES machine-field tests |
| Spanish reviewed by Alejandra against `docs/glossary.md` | ⏳ owner | Needs the owner's review |

## Logs & observability

| Item | Status | Evidence |
|---|---|---|
| JSON logs with request ID and locale; no PII or API keys in logs | ✅ | `app/core/observability.py`; `tests/test_observability.py::test_json_log_lines_carry_request_id_and_locale_but_no_query_or_key` |
| Sentry FE + BE; uptime monitor + alert | ⏳ owner | Needs accounts (Sentry DSN, an UptimeRobot or Better Stack monitor on `/health`). The post-deploy smoke test already opens a GitHub issue when production fails after a deploy. |
| `/health` (liveness) and `/ready` (DB + DuckDB) | ✅ | `tests/test_health.py`, `tests/test_observability.py::test_ready_checks_database_and_duckdb` |

## Rollback

| Item | Status | Evidence |
|---|---|---|
| Vercel instant rollback tested | ✅ | Drill on 2026-11-03: production rolled back to the slice-5e deployment (dashboard URL → 404), then promoted back (→ 200). `docs/runbook.md` §3 |
| Render rollback to previous deploy tested | ⏳ owner | Steps in `docs/runbook.md` §3; the Render dashboard is not reachable from the build environment |
| Runbook documents rollback + migration downgrade order | ✅ | `docs/runbook.md` §3 |

## Quality & docs

| Item | Status | Evidence |
|---|---|---|
| Coverage gates met; E2E green on prod in both locales | ✅ coverage gate, E2E on the production image · ⏳ E2E against the production URL | `pytest --cov-fail-under` in the API job (≥ 80 % `app/core`, ≥ 75 % overall); Playwright runs in CI against the production Docker image in 512 MB, in `/en` and `/es`. `post-deploy.yml` smoke-tests production. |
| WCAG AA: axe 0 serious in both locales; keyboard-only run of the main flow | ✅ axe · ⏳ keyboard run | Job "Web · axe…" (20 pages × 2 widths, axe-core 4.14 after PR #28). A manual keyboard-only run is for the owner. |
| README (EN) + ES summary, demo, architecture, how to run, API quickstart, skills table | ✅ | `README.md` (screenshots in `docs/screenshots/`) |
| License + dataset licenses/attribution displayed in the app | ✅ | Landing footer "Dataset licenses"; report notes cite source and license per dataset; `LICENSE` (MIT) |
| Light load: 20 VUs on `/kpis` + `/query`, p95 < 1.5 s warm | ✅ | `load/k6-kpis.js`, step in the stack job (fails the PR above the threshold) |
