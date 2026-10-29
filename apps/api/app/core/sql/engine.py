"""Run a guarded query on a dataset's star schema (DuckDB file, read-only)."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

from app.core.sql.guard import QueryRejected, check

TIMEOUT_S = 10.0
MAX_ROWS = 10_000


@dataclass
class QueryResult:
    columns: list[dict[str, str]]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    elapsed_ms: int
    meta: dict[str, Any] = field(default_factory=dict)


def _json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, bytes | bytearray):
        return value.hex()
    if isinstance(value, float) and value != value:
        return None
    return value


def connect(path: Path) -> duckdb.DuckDBPyConnection:
    """Read-only connection that cannot touch files, the network or its own settings."""
    con = duckdb.connect(
        str(path),
        read_only=True,
        config={
            "enable_external_access": False,
            "autoinstall_known_extensions": False,
            "autoload_known_extensions": False,
        },
    )
    con.execute("SET threads = 2")
    con.execute("SET memory_limit = '512MB'")
    con.execute("SET lock_configuration = true")
    return con


def run(
    path: Path, sql: str, timeout_s: float = TIMEOUT_S, max_rows: int = MAX_ROWS
) -> QueryResult:
    query = check(sql)
    con = connect(path)
    timer = threading.Timer(timeout_s, con.interrupt)
    started = time.perf_counter()
    timer.start()
    try:
        cur = con.execute(query)
        rows = cur.fetchmany(max_rows + 1)
        description = cur.description or []
    except duckdb.InterruptException as exc:
        raise QueryRejected("sql.timeout", seconds=int(timeout_s)) from exc
    except duckdb.ParserException as exc:
        raise QueryRejected("sql.syntax_error", message=str(exc).split("\n")[0][:300]) from exc
    except duckdb.Error as exc:
        if time.perf_counter() - started >= timeout_s:
            raise QueryRejected("sql.timeout", seconds=int(timeout_s)) from exc
        raise QueryRejected("sql.runtime_error", message=str(exc).split("\n")[0][:300]) from exc
    finally:
        timer.cancel()
        elapsed = int((time.perf_counter() - started) * 1000)
        con.close()
    truncated = len(rows) > max_rows
    rows = rows[:max_rows]
    return QueryResult(
        columns=[{"name": d[0], "type": str(d[1])} for d in description],
        rows=[[_json(v) for v in r] for r in rows],
        row_count=len(rows),
        truncated=truncated,
        elapsed_ms=elapsed,
    )


def describe(path: Path) -> list[dict[str, Any]]:
    """Tables, columns and row counts (for the schema panel)."""
    con = connect(path)
    try:
        tables = []
        names = [
            r[0]
            for r in con.execute(
                "SELECT table_name FROM information_schema.tables ORDER BY 1"
            ).fetchall()
        ]
        for name in names:
            cols = con.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = ? ORDER BY ordinal_position",
                [name],
            ).fetchall()
            count = con.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]  # noqa: S608 — names from the catalog
            tables.append(
                {"name": name, "rows": count, "columns": [{"name": c, "type": t} for c, t in cols]}
            )
        return tables
    finally:
        con.close()
