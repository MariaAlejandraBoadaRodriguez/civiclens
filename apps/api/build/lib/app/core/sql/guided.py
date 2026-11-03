"""The 12 guided queries of the SQL Lab. SQL is identical in every language; the question,
title and explanation live in the API catalogs (``guided.<query_id>.*``, EN + ES)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GuidedQuery:
    query_id: str
    concepts: tuple[str, ...]
    sql: str


GUIDED: tuple[GuidedQuery, ...] = (
    GuidedQuery(
        "top_suppliers",
        ("cte", "window_function", "join"),
        """WITH spend AS (
  SELECT s.supplier_name, SUM(f.amount_cad) AS total_cad
  FROM fact_contract f
  JOIN dim_supplier s USING (supplier_id)
  GROUP BY s.supplier_name
)
SELECT RANK() OVER (ORDER BY total_cad DESC) AS rnk,
       supplier_name,
       ROUND(total_cad, 2) AS total_cad,
       ROUND(total_cad / SUM(total_cad) OVER (), 4) AS share
FROM spend
ORDER BY rnk
LIMIT 10;""",
    ),
    GuidedQuery(
        "direct_award_share",
        ("aggregation",),
        """SELECT COALESCE(award_type, 'unknown') AS award_type,
       COUNT(*) AS contracts,
       ROUND(COUNT(*) / SUM(COUNT(*)) OVER (), 4) AS share_of_contracts,
       ROUND(SUM(amount_cad) / SUM(SUM(amount_cad)) OVER (), 4) AS share_of_spend
FROM fact_contract
GROUP BY 1
ORDER BY contracts DESC;""",
    ),
    GuidedQuery(
        "fiscal_year_end",
        ("join", "aggregation"),
        """SELECT d.fiscal_year,
       ROUND(SUM(f.amount_cad) FILTER (WHERE d.days_to_fy_end <= 30), 2) AS last_30_days_cad,
       ROUND(SUM(f.amount_cad) / NULLIF(COUNT(DISTINCT d.month), 0), 2) AS avg_month_cad,
       ROUND(SUM(f.amount_cad) FILTER (WHERE d.days_to_fy_end <= 30)
             / NULLIF(SUM(f.amount_cad) / NULLIF(COUNT(DISTINCT d.month), 0), 0), 2) AS spike_ratio
FROM fact_contract f
JOIN dim_date d USING (date_id)
GROUP BY d.fiscal_year
HAVING COUNT(*) >= 100
ORDER BY d.fiscal_year;""",
    ),
    GuidedQuery(
        "monthly_spend_by_entity",
        ("cte", "window_function", "join"),
        """WITH monthly AS (
  SELECT e.entity_name, d.month_start, SUM(f.amount_cad) AS spend_cad
  FROM fact_contract f
  JOIN dim_entity e USING (entity_id)
  JOIN dim_date d USING (date_id)
  GROUP BY ALL
)
SELECT entity_name, month_start, ROUND(spend_cad, 2) AS spend_cad,
       ROUND(spend_cad - LAG(spend_cad) OVER (PARTITION BY entity_name ORDER BY month_start), 2) AS change_cad
FROM monthly
ORDER BY entity_name, month_start
LIMIT 200;""",
    ),
    GuidedQuery(
        "suppliers_many_entities",
        ("join", "aggregation"),
        """SELECT s.supplier_name,
       COUNT(DISTINCT f.entity_id) AS entities,
       COUNT(*) AS contracts,
       ROUND(SUM(f.amount_cad), 2) AS total_cad
FROM fact_contract f
JOIN dim_supplier s USING (supplier_id)
GROUP BY s.supplier_name
HAVING COUNT(DISTINCT f.entity_id) >= 3
ORDER BY entities DESC, total_cad DESC
LIMIT 25;""",
    ),
    GuidedQuery(
        "new_supplier_cohorts",
        ("cte", "join", "aggregation"),
        """WITH cohorts AS (
  SELECT supplier_id, year(first_seen) AS cohort_year FROM dim_supplier
)
SELECT c.cohort_year,
       COUNT(DISTINCT c.supplier_id) AS new_suppliers,
       ROUND(SUM(f.amount_cad), 2) AS spend_cad
FROM cohorts c
JOIN fact_contract f USING (supplier_id)
GROUP BY c.cohort_year
ORDER BY c.cohort_year;""",
    ),
    GuidedQuery(
        "hhi_by_entity",
        ("cte", "window_function", "aggregation"),
        """WITH shares AS (
  SELECT entity_id, supplier_id,
         SUM(amount_cad) / SUM(SUM(amount_cad)) OVER (PARTITION BY entity_id) AS share
  FROM fact_contract
  WHERE amount_cad > 0
  GROUP BY entity_id, supplier_id
)
SELECT e.entity_name,
       ROUND(SUM(share * share), 4) AS hhi,
       COUNT(*) AS suppliers
FROM shares
JOIN dim_entity e USING (entity_id)
GROUP BY e.entity_id, e.entity_name
HAVING COUNT(*) >= 5
ORDER BY hhi DESC
LIMIT 20;""",
    ),
    GuidedQuery(
        "single_bidder",
        ("aggregation",),
        """SELECT award_type,
       COUNT(*) FILTER (WHERE n_bidders = 1) AS single_bidder,
       COUNT(n_bidders) AS with_bid_count,
       ROUND(COUNT(*) FILTER (WHERE n_bidders = 1) / NULLIF(COUNT(n_bidders), 0), 4) AS single_bidder_share
FROM fact_contract
GROUP BY award_type
ORDER BY single_bidder DESC;""",
    ),
    GuidedQuery(
        "split_contracts",
        ("cte", "window_function", "join"),
        """WITH ordered AS (
  SELECT f.entity_id, f.supplier_id, d.date, f.amount_cad,
         LAG(d.date) OVER (PARTITION BY f.entity_id, f.supplier_id ORDER BY d.date) AS previous_date
  FROM fact_contract f
  JOIN dim_date d USING (date_id)
)
SELECT e.entity_name, s.supplier_name,
       COUNT(*) AS contracts_within_7_days,
       ROUND(SUM(o.amount_cad), 2) AS total_cad
FROM ordered o
JOIN dim_entity e USING (entity_id)
JOIN dim_supplier s USING (supplier_id)
WHERE o.date - o.previous_date <= 7
GROUP BY ALL
ORDER BY contracts_within_7_days DESC
LIMIT 20;""",
    ),
    GuidedQuery(
        "spend_by_category",
        ("join", "aggregation"),
        """SELECT c.label_en, c.label_es,
       COUNT(*) AS contracts,
       ROUND(SUM(f.amount_cad), 2) AS total_cad,
       ROUND(MEDIAN(f.amount_cad), 2) AS median_cad
FROM fact_contract f
JOIN dim_category c USING (category_id)
GROUP BY ALL
ORDER BY total_cad DESC;""",
    ),
    GuidedQuery(
        "running_total",
        ("cte", "window_function"),
        """WITH monthly AS (
  SELECT d.month_start, SUM(f.amount_cad) AS spend_cad
  FROM fact_contract f
  JOIN dim_date d USING (date_id)
  GROUP BY d.month_start
)
SELECT month_start,
       ROUND(spend_cad, 2) AS spend_cad,
       ROUND(SUM(spend_cad) OVER (ORDER BY month_start), 2) AS running_total_cad
FROM monthly
ORDER BY month_start;""",
    ),
    GuidedQuery(
        "largest_per_entity",
        ("window_function", "subquery", "join"),
        """SELECT entity_name, rnk, contract_id, supplier_name, amount_cad
FROM (
  SELECT e.entity_name, f.contract_id, s.supplier_name, f.amount_cad,
         ROW_NUMBER() OVER (PARTITION BY f.entity_id ORDER BY f.amount_cad DESC) AS rnk
  FROM fact_contract f
  JOIN dim_entity e USING (entity_id)
  JOIN dim_supplier s USING (supplier_id)
  WHERE f.amount_cad IS NOT NULL
)
WHERE rnk <= 3
ORDER BY amount_cad DESC
LIMIT 60;""",
    ),
)
BY_ID = {q.query_id: q for q in GUIDED}
