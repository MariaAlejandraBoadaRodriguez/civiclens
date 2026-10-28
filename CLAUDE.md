# CivicLens — instructions for Claude

Read `docs/ROADMAP.md` (how/when, overrides the spec) and `docs/SPEC.md` (what) before any work.
Approved UI mockups: https://claude.ai/artifact/1FACLDLoSx3hTmETMXnVr9 — build screens to match them.

## Working agreement
- One session = one phase or slice from ROADMAP §4. The owner names it ("Day N, phase X").
- Work on a branch `phase-<n>-<short-name>`, open a PR to `main`, never push to `main` directly.
- PR description: what changed, how to verify (in `/en` and `/es`), DoD checklist from the roadmap.
- Talk to the owner (Alejandra) in **Spanish**; everything committed is in **English** (except `messages/es.json`, Spanish YAML catalogs and `*.es.md` docs).

## Conventions
- Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`).
- **i18n:** no hardcoded UI text. Every string goes through `t()` and is added to BOTH `apps/web/messages/en.json` and `es.json`. Run `python scripts/check_i18n.py`.
- UI language (EN/ES) ≠ data language (EN/FR/ES). Never translate data values. Canonical field names are always English.
- API: machine fields stay English and stable; human-readable text localized via `Accept-Language`.
- Fonts are self-hosted via `@fontsource` (no `next/font/google`: the build must work offline).

## Commands
```bash
# API
cd apps/api && pip install -e ".[dev]" && ruff check . && ruff format --check . && pytest
# Web
cd apps/web && npm ci && npm run lint && npm run typecheck && npm run build
# i18n
python scripts/check_i18n.py
```

## Suggested environment setup script (claude.ai/code)
```bash
cd apps/api && pip install -e ".[dev]" && cd ../web && npm ci
```
