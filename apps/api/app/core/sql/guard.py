"""Query guard for the SQL Lab (defense in depth, ADR-0002).

1. Static checks before DuckDB sees the query: size, a single statement, SELECT/WITH only,
   no write/admin keywords, no file / network / system table functions.
2. DuckDB's own parser must agree: exactly one statement of type SELECT.
3. Execution happens on a read-only connection with external access disabled and the
   configuration locked (see ``engine.py``), with a 10 s timeout and a 10,000-row cap.

Errors carry stable codes; the API localizes them.
"""

from __future__ import annotations

import re

import duckdb

MAX_SQL_CHARS = 20_000


class QueryRejected(ValueError):
    def __init__(self, code: str, **params: object) -> None:
        super().__init__(code)
        self.code = code
        self.params = params


FORBIDDEN_KEYWORDS = frozenset(
    """
    insert update delete merge upsert drop create alter truncate attach detach copy
    export import pragma install load call set reset vacuum checkpoint grant revoke begin
    commit rollback abort transaction use execute prepare deallocate summarize
    """.split()
)
FORBIDDEN_FUNCTIONS = re.compile(
    r"\b(read_\w+|write_\w+|parquet_\w+|sniff_csv|glob|duckdb_\w+|pragma_\w+|getenv|"
    r"current_setting|query|query_table|sqlite_\w+|postgres_\w+|mysql_\w+|iceberg_\w+|"
    r"delta_scan|httpfs\w*|load_aws_credentials|system|shell)\s*\(",
    re.IGNORECASE,
)
URL_OR_PATH = re.compile(r"'(?:[a-z0-9+]+://|/[^'\s]|\.{1,2}/|~/|[a-z]:\\)", re.IGNORECASE)

_STRING = re.compile(r"'(?:[^']|'')*'")
_IDENT = re.compile(r'"(?:[^"]|"")*"')
_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _strip(sql: str) -> str:
    """SQL without comments; string and quoted-identifier contents blanked out."""
    out = _BLOCK_COMMENT.sub(" ", sql)
    out = _LINE_COMMENT.sub(" ", out)
    out = _STRING.sub("''", out)
    return _IDENT.sub('""', out)


def check(sql: str) -> str:
    """Return the normalized query (trailing ``;`` removed) or raise ``QueryRejected``."""
    if not sql or not sql.strip():
        raise QueryRejected("sql.empty")
    if len(sql) > MAX_SQL_CHARS:
        raise QueryRejected("sql.too_long", limit=MAX_SQL_CHARS)
    if "\x00" in sql:
        raise QueryRejected("sql.forbidden_statement", keyword="NUL")
    body = _strip(sql).strip().rstrip(";").strip()
    if ";" in body:
        raise QueryRejected("sql.multiple_statements")
    first = re.match(r"\(*\s*(\w+)", body)
    if not first or first.group(1).lower() not in ("select", "with"):
        raise QueryRejected(
            "sql.forbidden_statement", keyword=(first.group(1).upper() if first else "?")
        )
    for word in re.findall(r"[a-z_]+", body.lower()):
        if word in FORBIDDEN_KEYWORDS:
            raise QueryRejected("sql.forbidden_statement", keyword=word.upper())
    if m := FORBIDDEN_FUNCTIONS.search(body):
        raise QueryRejected("sql.forbidden_function", function=m.group(1).lower())
    if URL_OR_PATH.search(_BLOCK_COMMENT.sub(" ", _LINE_COMMENT.sub(" ", sql))):
        raise QueryRejected("sql.forbidden_function", function="file or URL")
    try:
        statements = duckdb.extract_statements(sql)
    except duckdb.Error as exc:
        raise QueryRejected("sql.syntax_error", message=str(exc).split("\n")[0][:300]) from exc
    if len(statements) != 1:
        raise QueryRejected("sql.multiple_statements")
    if statements[0].type != duckdb.StatementType.SELECT:
        raise QueryRejected("sql.forbidden_statement", keyword=statements[0].type.name)
    return sql.strip().rstrip(";").strip()
