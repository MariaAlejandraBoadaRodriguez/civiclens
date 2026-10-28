# ADR-0005 · $0 hosting: Vercel + Render + Neon

- **Status:** Accepted · 2026-10-28

## Context
Constraint: infrastructure cost = $0/month for the MVP, with preview deploys per PR and a public URL a recruiter can open.

## Decision
| Piece | Platform | Why |
|---|---|---|
| Web (`apps/web`) | **Vercel** Hobby | Native Next.js, preview URL per PR, already connected |
| API (`apps/api`, Docker) | **Render** free web service | Runs our Dockerfile; Python + DuckDB without lambdas' size limits |
| App DB | **Neon** free Postgres | Branching for staging, PITR |
| Errors / uptime | Sentry free · UptimeRobot/Better Stack free | Phase 10 |

## Consequences
- ✅ $0, PR previews, platform rollbacks.
- ⚠️ Render free instances sleep after ~15 min → 30–60 s cold start. Mitigated with the `WakingUp` UI state (Phase 3 component), an uptime ping during demo hours, and fast boot (no model training at startup).
- ⚠️ Ephemeral disk on Render (see ADR-0002).
- ⚠️ Vercel Hobby is for non-commercial use — fine for a portfolio; revisit if an agency pilot becomes commercial.

## Alternatives considered
- **Fly.io:** similar, but no permanent free allowance for new accounts.
- **Single VPS:** cheapest at scale, but not $0 and more ops work.
