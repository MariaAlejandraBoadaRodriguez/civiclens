# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/) and [Semantic Versioning](https://semver.org/).

## [Unreleased]
### Added
- Phase 0: monorepo scaffold (Next.js 14 + next-intl EN/ES, FastAPI), Docker Compose, CI, repo templates.
- Phase 1: `docs/requirements.md` (27 user stories, MoSCoW, traceability), `docs/glossary.md` (74 EN↔ES terms), seed datasets (`data/seed/*.parquet`) with dataset cards and `scripts/fetch_seed.py`.
- Phase 3: design tokens (CSS variables + Tailwind), component library, `/en/design` + `/es/design`, locale formatting helpers, ESLint rule against hardcoded JSX strings, axe CI job, placeholder check in `check_i18n.py`.
