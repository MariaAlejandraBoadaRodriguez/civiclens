# ADR-0008 · Generic analysis core and declarative domain packs

- **Status:** Accepted · 2026-11-04 · extends [ADR-0006](0006-canonical-schema-and-recipes.md) (the star schema becomes one pack)

## Context
The owner requires the whole pipeline (Ingest → Clean → SQL → ML → Dashboard) to work for **any** tabular file — banking, elections, budgets, sales — not only public procurement. Before this change a non-procurement upload showed an empty star schema, "—" KPIs, supplier questions and a 500 on the dashboard. The owner also asked for **domain packs** (Government, Banking first; Marketing and Environmental next) that add domain questions, KPIs, models and layouts when they fit, without a new engine per domain.

## Decision
1. **Generic core.** Every dataset gets a typed DuckDB table `data` (in the same model file as before): one column per cleaned column, a safe snake_case name, a SQL type parsed with the column's own number locale and date order, and a *kind* (`number`, `integer`, `boolean`, `date`, `datetime`, `category`, `text`, `identifier`; `binary` flags two-valued columns). Pure functions in `app/core/analysis/`.
2. **Generated questions.** SQL questions are generated from the column profile (completeness, counts, target rates, numeric summaries, distributions, category × numeric, top/bottom segments, time trends, IQR outliers, correlations, identifier uniqueness). Every identifier is quoted; each question is executed once at build time and dropped if it fails, so the SQL Lab never shows a broken query. Texts are localized from `analysis.questions.<kind>.*` with the file's headers as parameters (headers are data: never translated).
3. **Domain packs are data.** One YAML file per pack in `app/core/packs/definitions/` (roles with accepted kinds and EN/ES/FR synonyms, goals, KPIs and questions as SQL templates `{role}`, `{a|b}`, `{positive:role}`, ML objectives, dashboard layout) plus its texts in the `packs` i18n catalog. A new pack needs no engine change.
4. **Role matching** scores each column against each role (exact synonym 0.95, multi-word 0.85, token 0.75, substring 0.55; the column kind must fit) and assigns each column once. The pack's fit score weighs key and target roles double; a pack can require a signal (`require_any`, e.g. Banking needs a default flag or days past due — amounts alone, as in a sales file, are not credit data). General is the floor (0.3).
5. **The user decides.** The suggestion is stored only when the user confirms it (`PUT /datasets/{id}/domain`, kept in `profile_json.domain`); until then the best suggestion above 0.3 applies. Roles that are not mapped drop the pack items that need them; the generic analysis always stays. A target's "positive" value is a yes-like word, else the minority value (events are the rarer case), and the user can change it.
6. **Procurement is the Government pack** (engine `procurement_star`): its roles are the canonical fields mapped at ingest, and only this pack builds the star schema. Switching to or from it rebuilds the model in a background job. Sample datasets keep their pack (they are shared).
7. **Sensitive attributes** (age, sex/gender, marital status, nationality) are pack roles flagged `sensitive`: shown with a badge, excluded from the pack fit score, used only for fairness checks — never as model inputs.
8. **Generic models (PR 3)** on the table `data`, each with an EN/ES model card:
   - *target model*: the task follows from the target's kind (flag → binary, ≤ 20 labels → multiclass, quantity → regression); histogram gradient boosting vs a naive baseline (majority class or mean) on a stratified 75/25 split; permutation importance; **leakage warnings** when one column alone predicts the target almost perfectly (≥ 0.95) or strongly (≥ 0.75) with an "after the outcome" name (`duration`, `status`, `paid` …);
   - **sensitive attributes** (pack roles, else header hints) are never inputs; a **fairness check** compares each group's share of positive predictions (four-fifths rule) and shows actual rates and true-positive rates next to it;
   - *anomalies* (Isolation Forest, naming the most unusual value), *segments* (k-means, k by silhouette, plain-language profiles), *forecast* on any date + quantity (the existing honest forecast, needs 24 months);
   - more than 20,000 rows are sampled with a fixed seed, and the card says so. Red flags stay procurement-only (409 otherwise).
9. **No 500 while views catch up.** Views not yet generic (dashboard, report, procurement models) answer 409 `domain.procurement_only` with a localized message pointing to the SQL Lab, until PRs 3–4 make them generic.

## Consequences
- ✅ Every acceptance fixture (`data/fixtures`) gets a typed table, ≥ 5 working questions with rows and KPIs with values; CI runs them end to end in the 512 MB image.
- ✅ Packs are reviewable YAML; adding Marketing and Environmental is a data change plus texts and tests.
- ⚠️ Heuristics (kinds, targets, year-like integers, role synonyms) can guess wrong; the UI shows every guess with its confidence and lets the user correct it.
- ⚠️ Generated SQL is built from safe names and escaped literals, not parameters; it is executed through the same read-only guard as user SQL.
