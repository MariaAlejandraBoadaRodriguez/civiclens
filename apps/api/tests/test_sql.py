"""SQL Lab (slice 5c): star schema, query guard, guided queries, KPIs and the API."""

import statistics
import time
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.core.sql import engine
from app.core.sql.guard import QueryRejected, check
from app.core.sql.guided import GUIDED
from app.core.sql.star_schema import TABLES, fiscal_year, fiscal_year_end
from app.db.session import SessionLocal
from app.main import app
from app.services import datasets as datasets_svc
from app.services import sql as svc

client = TestClient(app)
SEEDS = ("secop_co", "contracts_ca", "contracts_qc")

MALICIOUS = [
    "DROP TABLE fact_contract",
    "DELETE FROM fact_contract",
    "UPDATE fact_contract SET amount_cad = 0",
    "INSERT INTO dim_entity VALUES ('x', 'x', NULL, NULL, 'CO')",
    "CREATE TABLE stolen AS SELECT * FROM fact_contract",
    "ALTER TABLE fact_contract ADD COLUMN x INT",
    "TRUNCATE fact_contract",
    "SELECT 1; DROP TABLE fact_contract",
    "SELECT * FROM fact_contract /* ; */ ; DELETE FROM dim_date",
    "ATTACH '/tmp/other.db' AS other",
    "DETACH other",
    "COPY fact_contract TO '/tmp/out.csv'",
    "EXPORT DATABASE '/tmp/dump'",
    "PRAGMA database_list",
    "INSTALL httpfs",
    "LOAD httpfs",
    "SET enable_external_access = true",
    "RESET memory_limit",
    "CALL pragma_version()",
    "BEGIN TRANSACTION",
    "VACUUM",
    "SELECT * FROM read_csv('/etc/passwd')",
    "SeLeCt * FrOm ReAd_CsV_aUtO('/etc/hosts')",
    "SELECT * FROM read_parquet('s3://bucket/data.parquet')",
    "SELECT * FROM '/etc/passwd'",
    "SELECT * FROM 'https://evil.example/data.csv'",
    "SELECT getenv('HOME')",
    "SELECT current_setting('memory_limit')",
    "SELECT * FROM duckdb_settings()",
    "SELECT * FROM glob('/*')",
    "SELECT * FROM query('DROP TABLE fact_contract')",
    "SELECT * FROM sqlite_scan('/tmp/x.db', 't')",
    "WITH x AS (SELECT 1) DELETE FROM fact_contract",
    "SELECT * FROM fact_contract WHERE 1 = 1 UNION SELECT * FROM read_json('x.json')",
    "",
    "   -- only a comment",
    "SELECT 'x' || '" + "a" * 20_001 + "'",
    "SELEC * FROM fact_contract",
]


@pytest.fixture(scope="module")
def stars() -> dict:
    out = {}
    with SessionLocal() as session:
        for slug in SEEDS:
            ds = datasets_svc.resolve(session, slug)
            assert ds is not None
            out[slug] = (ds, svc.ensure_star(ds))
    return out


@pytest.mark.parametrize("sql", MALICIOUS)
def test_malicious_queries_are_rejected_by_the_guard(sql: str) -> None:
    with pytest.raises(QueryRejected):
        check(sql)


def test_at_least_twenty_malicious_queries() -> None:
    assert len(MALICIOUS) >= 20


def test_legitimate_queries_pass_the_guard() -> None:
    for sql in (
        "SELECT replace(supplier_name, 'S.A.S.', '') AS name, 'a / b' AS ratio FROM dim_supplier",
        "WITH t AS (SELECT 1 AS x) SELECT x FROM t;",
        "(SELECT 1) UNION ALL (SELECT 2)",
        "SELECT 'use; set' AS text_with_keywords",
    ):
        check(sql)


def test_the_connection_is_read_only_even_if_the_guard_is_bypassed(stars: dict) -> None:
    _, path = stars["secop_co"]
    con = engine.connect(path)
    try:
        for sql in (
            "DELETE FROM fact_contract",
            "SELECT * FROM read_csv('/etc/passwd')",
            "SET enable_external_access = true",
        ):
            with pytest.raises(Exception):  # noqa: B017, PT011 — any DuckDB error is fine
                con.execute(sql)
    finally:
        con.close()


def test_star_schema_tables_and_referential_integrity(stars: dict) -> None:
    for slug, (_, path) in stars.items():
        names = {t["name"]: t for t in engine.describe(path)}
        assert set(TABLES) <= set(names), slug
        assert names["fact_contract"]["rows"] > 1000
        for dim, key in (
            ("dim_entity", "entity_id"),
            ("dim_supplier", "supplier_id"),
            ("dim_date", "date_id"),
            ("dim_category", "category_id"),
            ("dim_currency", "currency"),
        ):
            orphans = engine.run(
                path,
                f"SELECT COUNT(*) FROM fact_contract f LEFT JOIN {dim} d USING ({key}) "  # noqa: S608
                f"WHERE f.{key} IS NOT NULL AND d.{key} IS NULL",
            ).rows[0][0]
            assert orphans == 0, (slug, dim)
        unique = engine.run(
            path, "SELECT COUNT(*) = COUNT(DISTINCT contract_id) FROM fact_contract"
        ).rows[0][0]
        assert unique, slug
        types = engine.run(path, "SELECT DISTINCT award_type FROM fact_contract").rows
        assert {r[0] for r in types} <= {"direct", "open", "limited", "other", None}


def test_fiscal_years() -> None:
    assert fiscal_year(date(2024, 3, 31), "CA") == 2024
    assert fiscal_year(date(2024, 4, 1), "CA") == 2025
    assert fiscal_year(date(2024, 12, 31), "CO") == 2024
    assert fiscal_year_end(2025, "QC") == date(2025, 3, 31)
    assert fiscal_year_end(2024, "CO") == date(2024, 12, 31)


def test_guided_queries_run_under_500_ms_p95(stars: dict) -> None:
    assert len(GUIDED) == 12
    for slug, (_, path) in stars.items():
        for q in GUIDED:
            timings = []
            for _ in range(5):
                started = time.perf_counter()
                result = engine.run(path, q.sql)
                timings.append((time.perf_counter() - started) * 1000)
            assert result.row_count > 0, (slug, q.query_id)
            p95 = statistics.quantiles(timings, n=20)[-1]
            assert p95 < 500, (slug, q.query_id, p95)


def test_row_cap_and_timeout(stars: dict) -> None:
    _, path = stars["secop_co"]
    capped = engine.run(path, "SELECT * FROM fact_contract", max_rows=10)
    assert capped.row_count == 10 and capped.truncated
    heavy = "SELECT COUNT(*) FROM range(10000000) a, range(10000000) b WHERE a.range + b.range = 7"
    with pytest.raises(QueryRejected) as err:
        engine.run(path, heavy, timeout_s=0.5)
    assert err.value.code == "sql.timeout"


def test_query_api_returns_rows_and_localized_problems() -> None:
    ok = client.post(
        "/api/v1/query",
        json={"dataset_id": "secop_co", "sql": GUIDED[0].sql},
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["row_count"] == len(body["rows"]) > 0
    assert {"name", "type"} <= set(body["columns"][0])
    bad = {"dataset_id": "secop_co", "sql": "DROP TABLE fact_contract"}
    en = client.post("/api/v1/query", json=bad, headers={"Accept-Language": "en"})
    es = client.post("/api/v1/query", json=bad, headers={"Accept-Language": "es"})
    assert en.status_code == es.status_code == 400
    assert en.headers["content-type"].startswith("application/problem+json")
    assert en.json()["code"] == es.json()["code"] == "sql.forbidden_statement"
    assert en.json()["params"] == es.json()["params"] == {"keyword": "DROP"}
    assert en.json()["title"] != es.json()["title"]
    missing = client.post("/api/v1/query", json={"dataset_id": "nope", "sql": "SELECT 1"})
    assert missing.status_code == 404


def test_schema_api() -> None:
    r = client.get("/api/v1/datasets/contracts_ca/schema")
    assert r.status_code == 200, r.text
    body = r.json()
    roles = {t["name"]: t["role"] for t in body["tables"]}
    assert roles["fact_contract"] == "fact" and roles["dim_supplier"] == "dimension"
    assert body["guardrails"] == {"read_only": True, "timeout_s": 10, "max_rows": 10_000}
    assert body["origin"] in ("clean", "recommended")


def test_guided_queries_api_identical_machine_fields_in_en_and_es() -> None:
    en = client.get("/api/v1/guided-queries", headers={"Accept-Language": "en"}).json()["items"]
    es = client.get("/api/v1/guided-queries", headers={"Accept-Language": "es"}).json()["items"]
    assert len(en) == len(es) == 12
    for a, b in zip(en, es, strict=True):
        assert (a["query_id"], a["sql"], a["concepts"]) == (b["query_id"], b["sql"], b["concepts"])
        for key in ("title", "question", "explanation"):
            assert a[key] and b[key] and a[key] != b[key], (a["query_id"], key)


def test_kpis_api() -> None:
    en = client.get("/api/v1/kpis/contracts_qc", headers={"Accept-Language": "en"}).json()
    es = client.get("/api/v1/kpis/contracts_qc", headers={"Accept-Language": "es"}).json()
    by_id = {k["kpi_id"]: k for k in en["items"]}
    assert {"total_spend", "contract_count", "direct_award_share", "hhi", "quality_score"} <= set(
        by_id
    )
    assert by_id["total_spend"]["currency"] == "CAD" and by_id["total_spend"]["value"] > 0
    assert 0 <= by_id["hhi"]["value"] <= 1
    assert 0 <= by_id["direct_award_share"]["value"] <= 1
    for a, b in zip(en["items"], es["items"], strict=True):
        assert (a["kpi_id"], a["value"], a["unit"]) == (b["kpi_id"], b["value"], b["unit"])
        assert a["name"] != b["name"]
