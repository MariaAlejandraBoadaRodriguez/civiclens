# ADR-0006 · Canonical schema, star schema and replayable cleaning recipes

- **Status:** Accepted · 2026-10-28

## Context
Three jurisdictions publish contracts with different headers (`fecha_de_firma`, `contract_date`, `date_signature`), languages, currencies and formats. Agencies need next month's file cleaned exactly like this month's.

## Decision
1. **Canonical schema** (English field names, never translated): `contract_id`, `entity_id`, `entity_name`, `supplier_id`, `supplier_name`, `signed_date`, `start_date`, `end_date`, `amount_original`, `currency`, `amount_cad`, `award_type`, `n_bidders`, `category_code`, `category_label_source`, `description`, `jurisdiction`. Headers are mapped from EN/FR/ES dictionaries + fuzzy matching with a confidence; < 0.8 is flagged for the user.
2. **Star schema** in DuckDB: `fact_contract(contract_id, entity_id, supplier_id, date_id, category_id, amount_original, currency, amount_cad, award_type, n_bidders)` + `dim_entity`, `dim_supplier`, `dim_date`, `dim_category(category_id, code, label_en, label_es, label_source)`, `dim_currency`.
3. **Cleaning operations are pure functions** `(DataFrame, args) → DataFrame` with no I/O and no randomness (or a fixed seed).
4. A **recipe** is a versioned JSON list of `{op, args}` steps (stored in `recipes.steps_json`). Replaying = folding the steps over the staged data. Header overrides and currency choices are steps too.
5. **Code export**: each op has a pandas and a SQL template → the recipe exports as a runnable script.
6. FX conversion uses a static, dated, cited table `data/fx_rates.csv` (ROADMAP A5).

## Consequences
- ✅ Same recipe + same input → identical output hash (tested in slice 5b); auditable decisions.
- ✅ Cross-jurisdiction KPIs on one schema and one currency.
- ⚠️ Slower to write than notebook code; each op needs tests and two code templates.
- ⚠️ Category labels: `label_source` keeps the original language value; `label_en`/`label_es` are curated mappings, never machine translation.
