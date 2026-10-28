# ADR-0003 · PostgreSQL (Neon) + SQLAlchemy 2 + Alembic for app data

- **Status:** Accepted · 2026-10-28

## Context
Besides contract data (ADR-0002) the API keeps transactional state: API keys, dataset metadata, versioned recipes, async jobs and an audit log. It needs integrity (FKs, unique constraints), backups and point-in-time restore, at $0.

## Decision
- **PostgreSQL** — Neon free tier in staging/prod (branch DB for staging), `postgres:16` in docker compose locally.
- **SQLAlchemy 2** typed ORM (`apps/api/app/db/models.py`), **Alembic** migrations (`app/db/migrations`), driver `psycopg` 3.
- Portable column types (`Uuid`, `JSON` → `JSONB` on Postgres, enums as `VARCHAR` + `CHECK`) so the migration test also runs on SQLite; CI runs it on Postgres 16 as well.
- Deterministic constraint names (naming convention) → stable diffs.
- Errors are stored as **codes** (`jobs.error_code`), never as text, so they can be rendered in any language (ADR-0007).
- Migrations run before the new API version receives traffic (Phase 9 CD).

## Schema (migration 001)
`api_keys(id, name, prefix, hash, scopes, created_at, last_used_at, revoked_at)` ·
`datasets(id, slug, name, source, format, data_lang, status, rows, columns, quality_score, raw_path, staged_path, profile_json, created_at, expires_at)` ·
`recipes(id, name, version, dataset_id → datasets SET NULL, steps_json, created_at)` ·
`jobs(id, type, status, dataset_id → datasets CASCADE, api_key_id → api_keys SET NULL, input_json, result_json, error_code, created_at, started_at, finished_at)` ·
`audit_log(id, actor, action, target, details_json, at)`. ERD in `docs/architecture.md`.

## Consequences
- ✅ Integrity + PITR backups for the data that must not be lost (keys, recipes).
- ✅ `tests/test_migrations.py` proves: upgrade on an empty DB, models == migrations (autogenerate diff empty), downgrade to base.
- ⚠️ Neon free tier sleeps → first query after idle is slower (combined with Render cold start; "Waking up the engine" UI).
- ⚠️ Non-native enums: no DB-level enum type, but adding a value is a simple `CHECK` change.

## Notes on deviations from the roadmap schema
- `api_keys.prefix`: public lookup prefix so a presented key is verified against one argon2 hash, not all of them.
- `datasets.slug/name/columns/raw_path/staged_path/profile_json/created_at`: needed by the UI and lineage.
- `recipes.name` + unique `(name, version)`: a recipe is a named, versioned artifact that outlives the 24 h upload it was built on (`dataset_id` → `SET NULL`).
- `jobs.dataset_id/api_key_id/started_at`, `audit_log.details_json`: traceability.
