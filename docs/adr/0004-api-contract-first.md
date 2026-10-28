# ADR-0004 · Contract-first REST API

- **Status:** Accepted · 2026-10-28

## Context
Agencies integrate once and expect the contract to stay stable; the web app consumes the same API. The API must be documented, versioned, secured with keys, rate-limited, and must handle heavy work (ingest, recipe replay, model runs) without a queue service.

## Decision
- **OpenAPI first:** `openapi.yaml` (3.1) at the repo root is the contract; FastAPI must match it (Schemathesis in CI from Phase 8). Spectral lints it in CI, including a custom rule that every operation lists `x-user-stories` (traceability to `docs/requirements.md`, also checked by `tests/test_openapi_contract.py`).
- **Versioning:** everything under `/api/v1`; breaking changes → `/api/v2`. `/health` (and `/ready` later) stay unversioned.
- **Auth:** `X-API-Key` header for agencies — scoped (`datasets:write`, `recipes:write`, `models:run`, `reports:read`), revocable, stored as argon2 hash with a public prefix. Read-only demo endpoints work anonymously with a lower rate limit. Admin endpoints (`/api/v1/keys`) use a bearer token issued after GitHub OAuth (single allow-listed admin).
- **Errors:** RFC 7807 `application/problem+json` with a stable `code` (+ `params`) and localized `title`/`detail` (ADR-0007).
- **Async jobs:** heavy endpoints return `202` + job id; jobs are rows in Postgres executed by FastAPI background tasks; clients poll `GET /api/v1/jobs/{id}`.
- **Rate limiting:** slowapi in-memory (single instance), `429` + `Retry-After`.

## Consequences
- ✅ Agencies get stable machine fields; the TS client is generated from the same file.
- ✅ No Redis/Celery to host.
- ⚠️ Jobs are lost if the instance restarts mid-run; they are idempotent and re-runnable by design.
- ⚠️ In-memory limits reset on restart; acceptable for one instance (ROADMAP §2).
