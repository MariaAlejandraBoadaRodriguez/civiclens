"""KPI catalog: one definition per KPI, computed in SQL on the star schema (spec M4).
Names and definitions are localized from ``kpi_catalog.<kpi_id>.*``; the SQL is shared."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KpiDefinition:
    kpi_id: str
    unit: str  # currency | count | ratio | index
    owner: str
    sql: str


CATALOG: tuple[KpiDefinition, ...] = (
    KpiDefinition(
        "total_spend", "currency", "finance", "SELECT SUM(amount_cad) FROM fact_contract"
    ),
    KpiDefinition("contract_count", "count", "procurement", "SELECT COUNT(*) FROM fact_contract"),
    KpiDefinition("avg_value", "currency", "finance", "SELECT AVG(amount_cad) FROM fact_contract"),
    KpiDefinition(
        "median_value", "currency", "finance", "SELECT MEDIAN(amount_cad) FROM fact_contract"
    ),
    KpiDefinition(
        "direct_award_share",
        "ratio",
        "procurement",
        "SELECT COUNT(*) FILTER (WHERE award_type = 'direct') / NULLIF(COUNT(award_type), 0) FROM fact_contract",
    ),
    KpiDefinition(
        "hhi",
        "index",
        "audit",
        "SELECT SUM(share * share) FROM (SELECT SUM(amount_cad) / SUM(SUM(amount_cad)) OVER () AS share "
        "FROM fact_contract WHERE amount_cad > 0 GROUP BY supplier_id)",
    ),
    KpiDefinition(
        "single_bidder_share",
        "ratio",
        "audit",
        "SELECT COUNT(*) FILTER (WHERE n_bidders = 1) / NULLIF(COUNT(n_bidders), 0) FROM fact_contract",
    ),
    KpiDefinition(
        "yoy_growth",
        "ratio",
        "finance",
        # The two most recent fiscal years that each hold at least 10 % of the contracts.
        "WITH y AS (SELECT d.fiscal_year AS fy, SUM(f.amount_cad) AS s, COUNT(*) AS n FROM fact_contract f "
        "JOIN dim_date d USING (date_id) GROUP BY 1), "
        "big AS (SELECT * FROM y WHERE n >= 0.1 * (SELECT SUM(n) FROM y) ORDER BY fy DESC LIMIT 2) "
        "SELECT CASE WHEN COUNT(*) = 2 THEN MAX(s) FILTER (WHERE fy = (SELECT MAX(fy) FROM big)) "
        "/ NULLIF(MAX(s) FILTER (WHERE fy = (SELECT MIN(fy) FROM big)), 0) - 1 END FROM big",
    ),
)
BY_ID = {k.kpi_id: k for k in CATALOG}
