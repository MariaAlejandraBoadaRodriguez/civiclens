# Acceptance fixtures — any tabular dataset

CivicLens must give meaningful, non-empty output at **every stage** (ingest → clean → SQL → ML →
dashboard → report) for **any** tabular file, never a 500. These seven public files, of very
different kinds, are the acceptance suite: CI runs the full flow on each of them against the API
image limited to 512 MB (`scripts/flow_check.py --fixtures data/fixtures`) and the API tests run
every stage on each (`apps/api/tests/test_any_dataset.py`).

Small samples, so CI stays fast; rebuilt deterministically with `scripts/build_fixtures.py`.

| File | Kind / domain pack | Rows | Format | Source | License |
|---|---|---|---|---|---|
| `bank_marketing.csv` | Marketing: phone campaigns of a Portuguese bank, target `y` (subscribed) | 5,000 of 41,188 | CSV, `;`, quoted | UCI Machine Learning Repository, *Bank Marketing* (`bank-additional-full.csv`), Moro, Cortez & Rita (2014), doi:10.24432/C5K306 — copy from [selva86/datasets](https://raw.githubusercontent.com/selva86/datasets/master/bank-additional-full.csv) | CC BY 4.0 |
| `german_credit.csv` | Banking: credit applicants, target `credit_risk` (1 = good) | 1,000 | CSV | UCI, *South German Credit* (Grömping 2019 correction of Statlog German Credit), doi:10.24432/C5X89F — copy from [selva86/datasets](https://raw.githubusercontent.com/selva86/datasets/master/GermanCredit.csv) | CC BY 4.0 |
| `air_quality_bucaramanga.csv` | Environmental: hourly PM10 at two stations, Jan–Mar 2021 | 3,904 | CSV | IDEAM, *Calidad del Aire en Colombia* (datos.gov.co `g4t8-zkc3`), filtered to Santander · PM10 · 2021-01 → 2021-03 | CC BY-SA 4.0 |
| `us_presidential_results.csv` | General · political: US presidential general-election results by state and candidate | 3,000 (sampled) | CSV | FiveThirtyEight, [election-results](https://github.com/fivethirtyeight/election-results) `election_results_presidential.csv`, 10 columns kept | CC BY 4.0 |
| `budget_colombia_pgn.csv` | General · government budget: national budget execution by entity, Spanish headers | 598 | CSV | Ministerio de Hacienda, *Ejecución Presupuestal del Presupuesto General de la Nación* (datos.gov.co `xjxk-qhsc`) | CC BY-SA 4.0 |
| `sales_adventureworks.xlsx` | General · company sales with dates (fictional company) | 3,000 (sampled) | XLSX, one sheet | Microsoft [Power BI Desktop samples](https://github.com/microsoft/powerbi-desktop-samples) *AdventureWorks Sales*: `Sales_data` joined to date, product, territory and order sheets | MIT |
| `sp500_companies.json` | General · mostly text/categorical: S&P 500 constituents | 503 | flat JSON | [datasets/s-and-p-500-companies](https://github.com/datasets/s-and-p-500-companies) `constituents.csv`, converted to JSON records | ODC-PDDL 1.0 |

Attribution: the samples are unmodified in content (rows are selected, columns kept or joined as
stated); the share-alike files (CC BY-SA) stay under CC BY-SA 4.0 in this folder.
