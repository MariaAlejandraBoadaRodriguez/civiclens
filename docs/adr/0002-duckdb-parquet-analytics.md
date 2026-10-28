# ADR-0002 · DuckDB over Parquet for analytics

- **Status:** Accepted · 2026-10-28

## Context
Datasets are 10k–50k rows (≤ 50 MB uploads). Users run aggregates, window functions and ad-hoc SQL (SQL Lab) and the API computes KPIs on demand. Budget is $0 and we want no extra server.

## Decision
- Every dataset is stored as **Parquet** files on the API's disk: `raw` (as ingested, strings), `staged` (typed, canonical schema), `clean` (after recipe) and the **star schema** (`fact_contract`, `dim_*`).
- **DuckDB** runs in-process over those files. SQL Lab opens a **read-only** connection per request, with a statement guard (single `SELECT`/`WITH`; no `ATTACH`, `COPY`, `PRAGMA`, `INSTALL`, `LOAD`), a 10 s timeout and a 10,000-row cap.
- Seed Parquet files are committed (`data/seed/`); uploads live under `data/uploads/` and are purged after 24 h.

## Consequences
- ✅ Millisecond aggregates on 50k rows; zero infrastructure; same engine locally and in prod.
- ✅ Parquet is the hand-off format for Power BI/Tableau export.
- ⚠️ Single node, not for multi-GB data (accepted; ROADMAP §2).
- ⚠️ Ephemeral disk on Render: uploads can vanish on redeploy — acceptable given the 24 h TTL; seed data is rebuilt from the repo at boot.
- ⚠️ SQL injection surface → guard + read-only connection + 20 malicious-query tests (slice 5c).

## Alternatives considered
- **Postgres for analytics too:** one database, but slower columnar scans and a write-capable SQL surface for SQL Lab.
- **BigQuery/Snowflake free tiers:** paid beyond quotas, network latency, vendor lock-in.
