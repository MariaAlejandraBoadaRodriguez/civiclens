# Capacity — 10 concurrent visitors (pre-launch)

Measured with k6 (`load/k6-visitors.js`) for the public pre-launch (citizen-oversight audience).

## The visitor flow
Each virtual visitor repeats one session, with 1–3 s of think time between pages:

- **Browse a sample** (all sessions): health, dataset list, profile, issues, one cleaning
  preview, SQL lab (schema, generated questions, two queries, KPIs), ML lab (latest red flags and
  forecast), dashboard, HTML report.
- **Check your own data** (every third session): upload a CSV (German credit, 1,000 rows), wait
  for the ingest job, read the domain step and the dashboard overview, train the prediction model.

Uploads, recipe applies and model runs are *heavy* calls. Jobs run one at a time on the instance,
so the 512 MB limit holds whatever the number of visitors; more visitors means a longer queue.

## Results

### Local, API pinned to one CPU core, production memory settings (fork runner, `MALLOC_ARENA_MAX=2`), 3 minutes

| Scenario | Sessions | Requests | Page p50 / p95 | HTML report p95 | Own-data flow p50 / p95 | 429 | 5xx | Checks | Peak memory (PSS) |
|---|---|---|---|---|---|---|---|---|---|
| A · 10 visitors, **one shared IP**, old limits (300 / 12 per min) | 94 | 2,055 | 22 / 894 ms | – | 31 / 51 s | **810** | 0 | 86 % | 369 MB |
| B · 10 visitors, **one IP each** (`TRUSTED_PROXY_HOPS=1`), old limits | 75 | 2,112 | 33 / 903 ms | 1.6 s | 41 / 48 s | 0 | 0 | 100 % | 359 MB |
| C · 10 visitors, **one shared IP**, new limits (1,200 / 30 per min) | 76 | 2,127 | 32 / 918 ms | 1.4 s | 40 / 50 s | 0 | 0 | 100 % | 367 MB |

### CI, the API image like Render free (512 MB, `--cpus=0.1`), new limits, 3 minutes each
Run by `.github/workflows/capacity.yml` on every PR that changes the load test or the limits, and
on demand against production (Actions → Capacity → Run workflow → `production`).

| Scenario | Sessions | Requests | Page p50 / p95 | HTML report p95 | Own-data flow p50 / p95 | 429 | 5xx | Checks | Peak memory |
|---|---|---|---|---|---|---|---|---|---|
| D · 10 visitors, one shared IP | 13 | 863 | 1.9 / 11.0 s | 13.4 s | 84 / 107 s | 0 | 0 | 100 % | 348 MiB (both runs), no OOM |
| E · 10 visitors, one IP each (right after D) | 13 | 1,025 | 1.7 / 10.6 s | 16.6 s | none finished in 90 s | 0 | 0 | 97.3 % | |

In E every upload was accepted, but the ingest jobs queued behind D's and E's other jobs for more
than the 90 s the test then waited; the test now waits up to 4 minutes so the next run reports the
real time instead of a failed check.

## Rate limit: per IP or global?
The limit is **already per caller**, not global: anonymous callers are counted per IP, and in
production (`render.yaml`: `TRUSTED_PROXY_HOPS=1`) that is the visitor's address as Render's
proxy reports it, not the proxy's own. A global bucket would have turned scenario B into
scenario A for everyone.

The problem the test found is **many people behind one IP**: a veeduría workshop on one Wi-Fi,
an office, or mobile networks that share public addresses (carrier-grade NAT, common in
Colombia). Ten visitors on one IP make ~530 requests and up to ~10 heavy calls a minute; the old
ceilings (300 and 12) answered 810 requests with 429 in three minutes. The new defaults (1,200
requests and 30 heavy calls per minute per IP) let a shared network of ten work with no 429 and
no extra memory, while one abusive client is still capped.

Per-visitor buckets (an anonymous session id) are not needed now: the id would come from the
client, so it could be forged to escape the limit, and it would need a server-side ceiling per
IP anyway. Revisit if feedback shows larger groups (a classroom of 30) on one network.

## What a visitor waits for
- Browsing pages: p95 under 1 s on one core; **p50 ~2 s, p95 ~11 s on Render free's 0.1 CPU**
  with ten visitors at once (the report ~13–17 s).
- The own-data flow: ~40 s at p50 on one core; **~1.5 min on 0.1 CPU**, more when several visitors
  upload at the same time — mostly queue time behind other visitors' jobs (one job at a time
  protects the 512 MB). The UI shows the phase and percent meanwhile.
- Nothing failed: no 5xx, no 429, no OOM. The limit for ten simultaneous visitors on the free
  instance is **CPU, not memory or the rate limit**. For a live workshop, move the API to a paid
  instance with at least 0.5 CPU for the day (same 512 MB settings); for scattered feedback
  visitors, free is enough.
- After the instance sleeps (Render free, 15 idle minutes): 30–60 s, once. The keep-warm workflow
  pings `/health` every 10 minutes from 07:00 to 23:00 Bogotá, and the landing page says
  "starting the engine" if a visitor still meets a cold start.
