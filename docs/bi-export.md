# Star schema export for Power BI and Tableau

CivicLens exports a dataset's star schema as a zip with one file per table:

```bash
# CSV (any tool)
curl -o star.zip "https://civiclens-api.onrender.com/api/v1/datasets/secop_co/export?format=csv"
# Parquet (smaller, keeps types; Power BI and Tableau both read it)
curl -o star.zip "https://civiclens-api.onrender.com/api/v1/datasets/secop_co/export?format=parquet"
```

The web app has the same export on the **Dashboard** ("Export for Power BI").

## Tables and keys

| Table | Key | Joins to the fact table on |
|---|---|---|
| `fact_contract` | `contract_id` | — |
| `dim_entity` | `entity_id` | `fact_contract.entity_id` |
| `dim_supplier` | `supplier_id` | `fact_contract.supplier_id` |
| `dim_date` | `date_id` (YYYYMMDD) | `fact_contract.date_id` |
| `dim_category` | `category_id` | `fact_contract.category_id` |
| `dim_currency` | `currency` | `fact_contract.currency` |

`amount_cad` is the amount converted to CAD with the rate of the contract's signing month, so the
three jurisdictions can be compared directly. `amount_original` + `currency` keep the source value.
`dim_date.fiscal_year` follows each jurisdiction's calendar (Colombia: January–December; Canada and
Québec: April–March, named by the year it ends).

## Power BI

1. **Get data → Folder** (or **Text/CSV** / **Parquet** per file), pick the unzipped folder, and
   load the six tables.
2. **Model view**: create one-to-many relationships from each `dim_*` key to the matching
   `fact_contract` column (single direction, dimension → fact). Mark `dim_date` as the date table
   (`date` column).
3. Measures that match the CivicLens KPI catalog:

```DAX
Total spend (CAD) = SUM ( fact_contract[amount_cad] )
Contracts = COUNTROWS ( fact_contract )
Direct award share =
    DIVIDE (
        CALCULATE ( COUNTROWS ( fact_contract ), fact_contract[award_type] = "direct" ),
        CALCULATE ( COUNTROWS ( fact_contract ), NOT ISBLANK ( fact_contract[award_type] ) )
    )
HHI =
    VAR total = [Total spend (CAD)]
    RETURN SUMX ( VALUES ( dim_supplier[supplier_id] ), DIVIDE ( [Total spend (CAD)], total ) ^ 2 )
```

## Tableau

1. **Connect → Text file** (CSV) or **More… → Parquet**, open `fact_contract`.
2. Drag the five dimension tables onto the canvas; Tableau proposes relationships on the matching
   key names (`entity_id`, `supplier_id`, `date_id`, `category_id`, `currency`).
3. Use `amount_cad` for every cross-jurisdiction view.

## Notes

- Values are exported exactly as cleaned; names are never translated. `dim_category` carries both
  `label_en` and `label_es`.
- Red flags are not part of the export: they are leads for human review and stay in the ML lab.
