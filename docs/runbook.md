# CivicLens runbook

Production: web **https://civiclens-eosin.vercel.app** (Vercel) · API **https://civiclens-api.onrender.com** (Render, Docker, free 512 MB).
Both deploy `main` only after every CI check passes (`render.yaml: autoDeployTrigger: checksPass`,
Vercel Deployment Check "civiclens: ci-passed"). `.github/workflows/post-deploy.yml` smoke-tests
production after each deploy and opens an issue with these rollback steps when it fails.

## 1. Is it up?

| Check | Command | Healthy answer |
|---|---|---|
| API alive | `curl -s https://civiclens-api.onrender.com/health` | `{"status":"ok",…,"commit":"<sha of main>"}` |
| API ready (DB + DuckDB) | `curl -s https://civiclens-api.onrender.com/ready` | `{"status":"ready",…}`; `503 server.not_ready` names the failing check |
| Full flow | `python scripts/flow_check.py --base https://civiclens-api.onrender.com --mode smoke --wait 120` | `OK: smoke flow` |
| Web | open `/en` and `/es` | landing renders, no "Waking up" after 90 s |

The free Render instance sleeps after 15 minutes idle; the first request takes ~50 s. The web
shows "Waking up the engine" during that time and a translated error with Retry after 90 s.

Every API answer carries `X-Request-ID`; every log line is JSON with `request_id` and `locale`.
To follow one request: Render → service → **Logs** → search the request ID.

## 2. Restart

- **API**: Render → `civiclens-api` → **Manual Deploy** ▾ → **Restart service** (keeps the image).
  Disk is ephemeral: uploads, saved recipes and jobs are lost; the three seed datasets and their
  star schemas are rebuilt from the image in about a minute (`WARM_SEEDS=true`).
- **Web**: stateless; Vercel → Deployments → current production → **⋯** → **Redeploy** only if
  an environment variable changed.

## 3. Rollback

Order: **web first if only the UI is broken; API first if the API is broken.** The web degrades
gracefully against an older API ("Not available on this API version"), never the reverse.

### Vercel (web) — tested 2026-11-03

1. Vercel → project `civiclens` → **Deployments**, filter *Production*.
2. On the last good deployment: **⋯** → **Instant Rollback** → **Continue**. Production switches
   in seconds; no rebuild.
3. Verify: the broken page is gone (`/en`, `/es`).
4. When the fix is merged and its deployment is READY: on that deployment **⋯** → **Promote**.
   After an instant rollback Vercel stops auto-assigning new production deployments until one is
   promoted: check that **Settings → Git → "Auto-assign Custom Production Domains"** is on again.

Drill on 2026-11-03 (release v1.0.0), via the Vercel API with the same effect as the buttons:

| Step | Deployment | Result |
|---|---|---|
| Before | `dpl_GrERgJ…` (PR #25, phase 6) | `/en/datasets/secop_co/dashboard` → 200 |
| Instant rollback | `dpl_Dqgrj…` (PR #24, slice 5e) | same URL → **404** (that version has no dashboard): rollback effective |
| Promote back | `dpl_GrERgJ…` | same URL → **200** "Public procurement · executive view" |

### Render (API) — documented, to be drilled by the owner

1. Render → `civiclens-api` → **Events** (or **Deploys**).
2. On the last good deploy: **Rollback** → confirm. Render redeploys that image (≈ 2–4 min).
3. Verify `/health` shows that deploy's `commit`, then `/ready`, then the smoke flow above.
4. Render keeps auto-deploying `main`; to stop it while investigating: **Settings → Build & Deploy
   → Auto-Deploy → Off**, and turn it back **On** after the fix.

### Database migrations

Production runs SQLite on the container disk (reset on every deploy), so a rollback needs no
migration step today. With a persistent database (Neon, Phase 9 option):

1. **Before** rolling the API back past a migration, downgrade it with the *newer* image still
   deployed: `alembic downgrade -1` (Render → **Shell**).
2. Then roll the API back.
3. Every migration's `downgrade()` is tested in CI (`tests/test_migrations.py::test_downgrade_to_base`,
   SQLite and Postgres 16).

## 4. Revoke an API key

1. Web: `/en/admin` (or `/es/admin`) → sign in with the allowlisted GitHub account.
2. Issued keys → **Revoke** → **Confirm: revoke now**.
3. The key is refused (401 `auth.invalid_key`) on the next request on every route; no restart.
4. If the **admin token** itself leaked: generate a new one (`openssl rand -hex 24`), set
   `ADMIN_API_TOKEN` in Render **and** Vercel (same value), redeploy both.

## 5. Restore

- **Seed datasets**: part of the image (`data/seed/*.parquet`, versioned in Git); a restart rebuilds them.
- **Uploads, recipes, jobs**: kept 24 h by design on the free tier and lost on restart; users
  re-upload. Recipes are portable: export as JSON, pandas or SQL from the Cleaning Studio.
- **FX table**: `data/fx_rates.csv` in Git; rebuild with `python scripts/fetch_fx.py`.

## 6. Load

`load/k6-kpis.js` (20 virtual users on `/kpis` + `/query`, warm) runs in CI against the API image
in 512 MB; target p95 < 1.5 s, < 1 % errors. Locally: `k6 run -e BASE=http://127.0.0.1:8000 load/k6-kpis.js`
with `RATE_LIMIT_ANONYMOUS=1000000` (the default 1200/min per IP would answer 429).

## 7. Incident checklist

1. Read the post-deploy issue (if any), `/health`, `/ready`, Render logs by request ID.
2. Roll back (§3) if users are affected and the cause is a deploy.
3. Write the fix with the test that would have caught it; CI green, including the 512 MB stack job.
4. Close the issue with the cause, the fix PR and the test.
