"""Export a recipe as a runnable pandas script and as equivalent DuckDB SQL.

The pandas script is the reference: it embeds ``locale_parse.py`` and ``ops.py`` verbatim
so running it on the staged Parquet reproduces the API output byte for byte (tested).
The SQL is a readable CTE chain for analysts; it follows the same rules with SQL
built-ins, and the pandas script remains the source of truth for edge cases.
"""

from __future__ import annotations

import pprint
import re
from pathlib import Path
from typing import Any

from app.core.cleaning.ops import AWARD_TYPES
from app.core.ingest.locale_parse import NULL_TOKENS

_CORE = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------- pandas


def _literal(value: Any) -> str:
    """Python literal for an argument value (dicts, lists, strings, numbers, booleans)."""
    return repr(value)


def pipeline_lines(steps: list[dict[str, Any]]) -> list[str]:
    lines = []
    for step in steps:
        args = ", ".join(f"{k}={_literal(v)}" for k, v in step.get("args", {}).items())
        lines.append(f"df = {step['op']}(df, ctx{', ' + args if args else ''})")
    return lines


def pandas_preview(steps: list[dict[str, Any]]) -> str:
    """Short version shown in the Cleaning Studio (helpers omitted)."""
    head = [
        'ctx = Context(fx=FxTable.from_csv("fx_rates.csv"))',
        'df = read_staged("staged.parquet")',
    ]
    return "\n".join(head + pipeline_lines(steps) + ['df.to_csv("clean.csv", index=False)'])


def _module_source(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"^from __future__ import annotations\n", "", text, flags=re.MULTILINE)
    # ops.py imports locale_parse; in the script both live in one file.
    return re.sub(
        r"^from app\.core\.ingest\.locale_parse import \([^)]*\)\n", "", text, flags=re.MULTILINE
    )


def pandas_script(recipe: dict[str, Any]) -> str:
    """Self-contained script: python clean.py staged.parquet fx_rates.csv clean.csv"""
    body = "\n".join("    " + line for line in pipeline_lines(recipe["steps"]))
    return f'''"""CivicLens cleaning recipe "{recipe["name"]}" v{recipe["version"]} — generated code.

Usage: python clean.py staged.parquet fx_rates.csv clean.csv
Requires: pandas, pyarrow. Prints the SHA-256 of the output (same as the CivicLens API).
"""

from __future__ import annotations

import sys

RECIPE = {pprint.pformat(recipe, width=88, sort_dicts=False)}

# ---- locale_parse.py (CivicLens) ------------------------------------------------
{_module_source(_CORE / "ingest" / "locale_parse.py")}

# ---- ops.py (CivicLens) -----------------------------------------------------------
{_module_source(_CORE / "cleaning" / "ops.py")}


def read_staged(path: str) -> pd.DataFrame:
    df = pd.read_parquet(path).astype(object)
    return df.where(df.notna(), None)


def main(staged: str, fx: str, output: str) -> str:
    ctx = Context(fx=FxTable.from_csv(fx))
    df = read_staged(staged)
{body}
    df.to_csv(output, index=False)
    return output_hash(df)


if __name__ == "__main__":
    print(main(*sys.argv[1:4]))
'''


# --------------------------------------------------------------------------- SQL


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _s(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _norm(expr: str) -> str:
    return f"lower(strip_accents(trim(regexp_replace(CAST({expr} AS VARCHAR), '\\s+', ' ', 'g'))))"


_NUMBER = (
    "CASE WHEN regexp_matches(trim({c}), ',[0-9]{{1,2}}$') "
    "THEN TRY_CAST(replace(regexp_replace(trim({c}), '[ .\u00a0\u202f''$]|[A-Za-z]', '', 'g'), ',', '.') AS DOUBLE) "
    "ELSE TRY_CAST(regexp_replace(trim({c}), '[ ,\u00a0\u202f''$]|[A-Za-z]', '', 'g') AS DOUBLE) END"
)


def _step_sql(step: dict[str, Any], prev: str, columns: list[str]) -> tuple[str, list[str]]:
    """SELECT for one step over CTE ``prev``; returns the SQL and the resulting columns."""
    op, a = step["op"], step.get("args", {})
    cols = list(columns)
    if op == "rename_columns":
        renames = ", ".join(f"{_q(k)} AS {_q(v)}" for k, v in a["mapping"].items() if k in cols)
        cols = [a["mapping"].get(c, c) for c in cols]
        return (
            f"SELECT * RENAME ({renames}) FROM {prev}" if renames else f"SELECT * FROM {prev}"
        ), cols
    if op == "drop_columns":
        drop = [c for c in a["columns"] if c in cols]
        cols = [c for c in cols if c not in drop]
        return f"SELECT * EXCLUDE ({', '.join(map(_q, drop))}) FROM {prev}", cols
    if op == "mask_columns":
        salt = a.get("salt", "civiclens")
        repl = ", ".join(
            f"CASE WHEN {_q(c)} IS NULL OR {_q(c)} = '' THEN NULL ELSE 'MASK-' || left(sha256({_s(salt + ':')} || {_q(c)}), 10) END AS {_q(c)}"
            for c in a["columns"]
        )
        return f"SELECT * REPLACE ({repl}) FROM {prev}", cols
    if op == "standardize_nulls":
        tokens = ", ".join(_s(t) for t in sorted(NULL_TOKENS))
        targets = a.get("columns") or [c for c in cols if not c.startswith("__")]
        repl = ", ".join(
            f"CASE WHEN {_norm(_q(c))} IN ({tokens}) THEN NULL ELSE {_q(c)} END AS {_q(c)}"
            for c in targets
        )
        return f"SELECT * REPLACE ({repl}) FROM {prev}", cols
    if op == "drop_duplicates":
        data = [c for c in cols if not c.startswith("__")]
        keys = ", ".join(
            _norm(_q(c)) if a.get("mode") == "near" else f"CAST({_q(c)} AS VARCHAR)" for c in data
        )
        order = "__rowid DESC" if a.get("keep") == "last" else "__rowid"
        rank = f"row_number() OVER (PARTITION BY {keys} ORDER BY {order})"
        if a.get("keep") == "flag":
            return f"SELECT *, {rank} > 1 AS is_duplicate FROM {prev}", cols + ["is_duplicate"]
        return f"SELECT * FROM {prev} QUALIFY {rank} = 1", cols
    if op == "parse_numbers":
        c = _q(a["column"])
        return f"SELECT * REPLACE ({_NUMBER.format(c=c)} AS {c}) FROM {prev}", cols
    if op == "normalize_timezones":
        c = _q(a["column"])
        expr = (
            f"strftime(TRY_CAST({c} AS TIMESTAMPTZ) AT TIME ZONE 'UTC', '%Y-%m-%dT%H:%M:%S')"
            if a.get("to", "utc") == "utc"
            else f"regexp_replace({c}, '([+-][0-9]{{2}}:?[0-9]{{2}}|Z)$', '')"
        )
        return f"SELECT * REPLACE (COALESCE({expr}, {c}) AS {c}) FROM {prev}", cols
    if op == "parse_dates":
        c = _q(a["column"])
        slashed = "'%d/%m/%Y'" if a.get("dayfirst", True) else "'%m/%d/%Y'"
        expr = (
            f"COALESCE(TRY_CAST({c} AS TIMESTAMP), TRY_STRPTIME({c}, {slashed}), "
            f"TRY_STRPTIME({c}, '%Y/%m/%d'), TRY_STRPTIME({c}, '%Y%m%d'))"
        )
        return f"SELECT * REPLACE ({expr} AS {c}) FROM {prev}", cols
    if op == "convert_currency":
        to, amt = a.get("to", "CAD"), _q(a.get("amount", "amount_original"))
        cur, dt = _q(a.get("currency", "currency")), _q(a.get("date", "signed_date"))
        month = f"strftime(TRY_CAST(s.{dt} AS TIMESTAMP), '%Y-%m')"
        value = f"CASE WHEN upper(trim(s.{cur})) = {_s(to)} THEN s.{amt} ELSE round(s.{amt} * f.cad_per_unit / t.cad_per_unit, 2) END"
        join = (
            f"FROM {prev} s LEFT JOIN fx_rates f ON f.currency = upper(trim(s.{cur})) AND f.month = {month} "
            f"LEFT JOIN fx_rates t ON t.currency = {_s(to)} AND t.month = {month}"
        )
        if a.get("mode") == "add_column":
            new = f"amount_{to.lower()}"
            return f"SELECT s.*, {value} AS {_q(new)} {join}", cols + [new]
        return f"SELECT s.* REPLACE ({value} AS {amt}, {_s(to)} AS {cur}) {join}", cols
    if op == "normalize_text":
        c = _q(a["column"])
        expr = f"trim(regexp_replace({c}, '\\s+', ' ', 'g'))" if a.get("trim", True) else c
        if a.get("remove_accents"):
            expr = f"strip_accents({expr})"
        expr = {
            "upper": f"upper({expr})",
            "lower": f"lower({expr})",
            "title": f"initcap({expr})",
        }.get(a.get("case", "keep"), expr)
        return f"SELECT * REPLACE ({expr} AS {c}) FROM {prev}", cols
    if op == "unify_variants":
        c = _q(a["column"])
        canon = (
            f"(SELECT k, arg_max(v, n) AS canonical FROM (SELECT {_norm(c)} AS k, trim({c}) AS v, count(*) AS n "
            f"FROM {prev} WHERE {c} IS NOT NULL GROUP BY ALL) GROUP BY k)"
        )
        return (
            f"SELECT p.* REPLACE (u.canonical AS {c}) FROM {prev} p LEFT JOIN {canon} u ON u.k = {_norm('p.' + c)}",
            cols,
        )
    if op == "handle_missing":
        c, action = _q(a["column"]), a.get("action", "keep")
        if action == "drop_rows":
            return f"SELECT * FROM {prev} WHERE {c} IS NOT NULL", cols
        if action == "fill":
            return (
                f"SELECT * REPLACE (COALESCE({c}, {_s(str(a.get('value')))}) AS {c}) FROM {prev}",
                cols,
            )
        if action == "flag":
            return f"SELECT *, {c} IS NULL AS {_q(a['column'] + '_missing')} FROM {prev}", cols + [
                a["column"] + "_missing"
            ]
        return f"SELECT * FROM {prev}", cols
    if op == "handle_outliers":
        c, k, action = _q(a["column"]), a.get("k", 3.0), a.get("action", "flag")
        fences = (
            f"(SELECT power(10, q1 - {k} * (q3 - q1)) AS lo, power(10, q3 + {k} * (q3 - q1)) AS hi FROM "
            f"(SELECT quantile_disc(log10({c}), 0.25) AS q1, quantile_disc(log10({c}), 0.75) AS q3 FROM {prev} WHERE {c} > 0))"
        )
        if action == "cap":
            return (
                f"SELECT p.* REPLACE (round(least(greatest(p.{c}, b.lo), b.hi), 2) AS {c}) FROM {prev} p, {fences} b",
                cols,
            )
        if action == "flag":
            name = a["column"] + "_outlier"
            return (
                f"SELECT p.*, COALESCE(p.{c} < b.lo OR p.{c} > b.hi, false) AS {_q(name)} FROM {prev} p, {fences} b",
                cols + [name],
            )
        return f"SELECT * FROM {prev}", cols
    if op == "cast_type":
        c = _q(a["column"])
        target = {"integer": "BIGINT", "number": "DOUBLE", "string": "VARCHAR"}[
            a.get("to", "integer")
        ]
        return f"SELECT * REPLACE (TRY_CAST({c} AS {target}) AS {c}) FROM {prev}", cols
    if op == "standardize_categories":
        c = _q(a["column"])
        table = AWARD_TYPES if a.get("mapping", "award_type") == "award_type" else a["mapping"]
        whens = " ".join(f"WHEN {_s(k)} THEN {_s(v)}" for k, v in table.items())
        name = a["column"] + "_source"
        return (
            f"SELECT * REPLACE (CASE {_norm(c)} {whens} ELSE 'other' END AS {c}), {c} AS {_q(name)} FROM {prev}",
            cols + [name],
        )
    raise ValueError(f"no SQL template for {op}")


def sql_script(recipe: dict[str, Any], columns: list[str]) -> str:
    """DuckDB SQL: ``staged`` and ``fx_rates`` are the two inputs (Parquet / CSV)."""
    ctes = ["s0 AS (SELECT row_number() OVER () AS __rowid, * FROM staged)"]
    cols = ["__rowid", *columns]
    for i, step in enumerate(recipe["steps"], start=1):
        sql, cols = _step_sql(step, f"s{i - 1}", cols)
        ctes.append(f"-- {i}. {step['op']}\ns{i} AS ({sql})")
    last = f"s{len(recipe['steps'])}"
    header = (
        f'-- CivicLens cleaning recipe "{recipe["name"]}" v{recipe["version"]} (DuckDB SQL)\n'
        "-- CREATE VIEW staged AS SELECT * FROM 'staged.parquet';\n"
        "-- CREATE VIEW fx_rates AS SELECT * FROM 'fx_rates.csv';\n"
    )
    return (
        header
        + "WITH\n"
        + ",\n".join(ctes)
        + f"\nSELECT * EXCLUDE (__rowid) FROM {last} ORDER BY __rowid;\n"
    )


def sql_preview(steps: list[dict[str, Any]], columns: list[str]) -> str:
    return sql_script({"name": "preview", "version": 0, "steps": steps}, columns)
