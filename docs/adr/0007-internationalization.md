# ADR-0007 · Internationalization

- **Status:** Proposed · 2026-10-28 — **requires owner approval** (Phase 4 DoD)

## Context
Two independent language concepts (ROADMAP §0):
- **UI language** — what the user reads: **EN or ES**, user-selectable.
- **Data language** — what the file contains: **EN, FR or ES**, auto-detected.

Agencies consume the API from systems in either language and must not have their parsers break when the language changes. Spanish must be neutral Latin American Spanish, reviewed by the owner (A7); no runtime machine translation.

## Decision
1. **Ownership of strings**
   - **Frontend** owns UI strings: `apps/web/messages/{en,es}.json`, namespaced by screen (`common`, `nav`, `landing`, `ingest`, `clean`, `sql`, `ml`, `dashboard`, `design`). Every string through `t()`; ESLint blocks JSX literals.
   - **Backend** owns domain content the API returns: issue-card texts, KPI names/definitions, guided-query explanations, model cards, red-flag reasons, report templates, error titles → `apps/api/app/i18n/{en,es}/*.yaml`, keyed by stable IDs (e.g. `issue.mixed_currency.why`, `error.sql.forbidden_statement.title`).
2. **API language negotiation**
   - `Accept-Language` → `es` if the best match starts with `es`, else `en`. A `lang` query parameter overrides it only on `GET /api/v1/reports/{id}`.
   - Every response with human text sets `Content-Language`.
   - **Machine fields are language-neutral and identical across languages**: `issue_type`, `issue_id`, `kpi_id`, `field`, `code`, `option_id`, numbers, dates (ISO 8601), currency codes. Localized fields: `title`, `message`, `what`, `why`, `hint`, `label`, `explanation`, `definition`, `detail`.
   - Errors are RFC 7807 with stable `code` + `params`; `title`/`detail` rendered from the catalog in the negotiated language. The DB stores codes only.
3. **Formatting**: the API returns raw numbers and ISO dates; the frontend formats with `Intl` for the UI locale (`en-CA`, `es-CO`), currency code always visible. Server-generated reports format with Babel using the report language.
4. **Data language** detection (`langdetect` + header dictionaries) is stored per dataset and per column (`datasets.data_lang`, `profile_json`). It never changes the UI language, and **data values are never translated**. Canonical field *labels* are translated; field *names* are not.
5. **Routing (web)**: locale-prefixed URLs (`/en/...`, `/es/...`), detection from `NEXT_LOCALE` cookie → `Accept-Language` → `en`; `<html lang>` and `hreflang` alternates per page.
6. **Quality gates**: `scripts/check_i18n.py` (same keys and ICU placeholders in EN/ES; extended to the backend YAML catalogs in slice 5b), Playwright check for English strings on `/es` pages (Phase 8), glossary `docs/glossary.md` as the terminology reference.

## Consequences
- ✅ Stable API contracts in both languages; tests can assert "same request in en/es → identical machine fields".
- ✅ Domain explanations live in one place per language and are testable for missing keys.
- ⚠️ Two catalogs to maintain on each side; every new string is written twice (accepted trade-off, ROADMAP §2).
- ⚠️ No French UI (French *data* is fully supported). Adding a UI language = new catalogs + one entry in `routing.locales` and in the negotiation function.

## Alternatives considered
- **Translate on the client from English API text:** breaks for agencies calling the API directly — rejected.
- **Runtime machine translation (LLM/API):** cost, non-determinism, no review — rejected (A7).
- **Localized field names in API payloads:** breaks parsers between languages — rejected.
