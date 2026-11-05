"""Guided SQL questions generated from the columns of the uploaded file.

The questions are specific to the file: they name its columns and use only SQL that fits each
column's kind. Every identifier is quoted (``"default"`` is a reserved word in SQL). The texts are
localized from ``analysis.questions.<kind>.*`` with the column names as parameters; the SQL is
the same in every language. The service runs each question once and drops any that fails, so
the SQL Lab never shows a broken query.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.core.analysis.table import NUMERIC_KINDS, TEMPORAL_KINDS, ColumnMeta

TARGET_HINT = re.compile(
    r"(^|_)(y|target|label|class|outcome|default|defaulted|churn|churned|converted|conversion|"
    r"subscribed|winner|won|approved|fraud|risk|credit_risk|response|clicked|bought|flag)($|_)"
)
MAX_QUESTIONS = 14


def q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def lit(text: str) -> str:
    return "'" + str(text).replace("'", "''") + "'"


@dataclass
class Question:
    query_id: str
    kind: str  # catalog key: analysis.questions.<kind>
    sql: str
    params: dict[str, str] = field(default_factory=dict)  # column labels for the texts
    concepts: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)  # pack goals this question serves first
    source: str = "generic"  # generic | <pack id>

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "kind": self.kind,
            "sql": self.sql,
            "params": self.params,
            "concepts": self.concepts,
            "goals": self.goals,
            "source": self.source,
        }


@dataclass
class Picks:
    """The columns the generic analysis leans on (also used by the dashboard and models)."""

    categories: list[ColumnMeta]
    numbers: list[ColumnMeta]
    target: ColumnMeta | None
    dates: list[ColumnMeta]


def positive_expr(meta: ColumnMeta, positive: str | None = None) -> str:
    """SQL that is TRUE for the "positive" value of a binary column (yes / 1 / the chosen one)."""
    col = q(meta.name)
    if positive is not None:
        if meta.kind == "boolean":
            return f"{col} = {'TRUE' if str(positive).lower() in ('true', '1', 'yes') else 'FALSE'}"
        return f"CAST({col} AS VARCHAR) = {lit(positive)}"
    if meta.kind == "boolean":
        return f"{col} = TRUE"
    values = sorted(str(t["value"]) for t in meta.top)
    if set(values) == {"0", "1"} or set(values) == {"0.0", "1.0"}:
        return f"{col} = 1"
    return f"{col} = (SELECT MAX({col}) FROM data)"


def _zero_one(meta: ColumnMeta) -> bool:
    values = {str(t["value"]) for t in meta.top}
    return values in ({"0", "1"}, {"0.0", "1.0"})


def year_like(meta: ColumnMeta) -> bool:
    """Whole numbers between 1500 and 2100 (election cycle, year founded): a time label, not a
    quantity to average or sum."""
    return (
        meta.kind == "integer"
        and meta.min is not None
        and 1500 <= float(meta.min)
        and float(meta.max) <= 2100
    )


def pick(metas: list[ColumnMeta]) -> Picks:
    cats = [
        m for m in metas if m.kind == "category" and 2 <= m.distinct <= 60 and m.null_share < 0.6
    ]
    cats.sort(key=lambda m: (m.null_share > 0.2, abs(m.distinct - 8), m.distinct))
    nums = [
        m
        for m in metas
        if m.kind in NUMERIC_KINDS
        and not m.binary
        and m.distinct > 2
        and m.null_share < 0.8
        and not year_like(m)
    ]
    nums.sort(key=lambda m: (m.null_share > 0.2, -min(m.distinct, 1000)))
    binaries = [m for m in metas if m.binary and m.distinct == 2]
    named = [m for m in binaries if TARGET_HINT.search(m.name)]
    # Unnamed: only yes/no or 0/1 flags (two station altitudes are not an outcome).
    flags = [m for m in binaries if m.kind == "boolean" or _zero_one(m)]
    target = named[-1] if named else (flags[-1] if flags else None)
    dates = [m for m in metas if m.kind in TEMPORAL_KINDS and m.distinct > 1]
    return Picks(cats, nums, target, dates)


def _label(m: ColumnMeta) -> str:
    return m.source


def generate(metas: list[ColumnMeta], rows: int) -> list[Question]:
    p = pick(metas)
    out: list[Question] = []
    usable = [m for m in metas if m.kind != "text"][:20]

    # 1. Completeness of every column.
    if usable:
        parts = [
            f"SELECT {lit(m.source)} AS column_name, COUNT({q(m.name)}) AS filled, "
            f"COUNT(*) - COUNT({q(m.name)}) AS missing, "
            f"ROUND(100.0 * (COUNT(*) - COUNT({q(m.name)})) / COUNT(*), 1) AS missing_pct FROM data"
            for m in usable
        ]
        out.append(
            Question(
                "completeness",
                "completeness",
                "\nUNION ALL\n".join(parts) + "\nORDER BY missing DESC, column_name",
                {"rows": str(rows)},
                ["COUNT", "UNION ALL"],
            )
        )

    # Labels with many values (sub-industry, city) still answer "which are the most frequent?"
    # when the file has few low-cardinality categories (mostly text files).
    wide = [
        m
        for m in metas
        if m.kind == "category" and m not in p.categories and m.distinct >= 2 and m.null_share < 0.6
    ]
    labels = p.categories + wide

    # 2. Counts and shares per category.
    for m in labels[:2]:
        out.append(
            Question(
                f"counts_{m.name}",
                "category_counts",
                f"SELECT {q(m.name)}, COUNT(*) AS rows,\n"
                f"       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS share_pct\n"
                f"FROM data\nGROUP BY 1\nORDER BY rows DESC\nLIMIT 20",
                {"column": _label(m)},
                ["GROUP BY", "window function"],
            )
        )

    # 3. Rate of the binary / target-like column by category.
    if p.target is not None:
        t = p.target
        pos = positive_expr(t)
        for m in [c for c in p.categories if c.name != t.name][:2]:
            out.append(
                Question(
                    f"rate_{t.name}_by_{m.name}",
                    "target_rate",
                    f"SELECT {q(m.name)}, COUNT(*) AS rows,\n"
                    f"       ROUND(100.0 * AVG(CASE WHEN {pos} THEN 1 ELSE 0 END), 1) AS rate_pct\n"
                    f"FROM data\nGROUP BY 1\nHAVING COUNT(*) >= 5\nORDER BY rate_pct DESC\nLIMIT 20",
                    {"target": _label(t), "column": _label(m)},
                    ["CASE WHEN", "AVG"],
                )
            )

    # 4. Numeric summaries.
    if p.numbers:
        parts = [
            f"SELECT {lit(m.source)} AS column_name, MIN({q(m.name)}) AS min,\n"
            f"       ROUND(quantile_cont({q(m.name)}, 0.25), 2) AS p25,\n"
            f"       ROUND(MEDIAN({q(m.name)}), 2) AS median,\n"
            f"       ROUND(quantile_cont({q(m.name)}, 0.75), 2) AS p75,\n"
            f"       MAX({q(m.name)}) AS max, ROUND(AVG({q(m.name)}), 2) AS mean,\n"
            f"       ROUND(STDDEV({q(m.name)}), 2) AS std_dev FROM data"
            for m in p.numbers[:5]
        ]
        out.append(
            Question(
                "numeric_summary",
                "numeric_summary",
                "\nUNION ALL\n".join(parts),
                {"columns": ", ".join(_label(m) for m in p.numbers[:5])},
                ["MEDIAN", "quantile_cont", "STDDEV"],
            )
        )
        x = q(p.numbers[0].name)
        out.append(
            Question(
                f"distribution_{p.numbers[0].name}",
                "distribution",
                f"WITH s AS (SELECT MIN({x}) AS lo, (MAX({x}) - MIN({x})) / 10.0 AS w\n"
                f"           FROM data WHERE {x} IS NOT NULL),\n"
                f"b AS (SELECT LEAST(CAST(FLOOR(({x} - s.lo) / NULLIF(s.w, 0)) AS INTEGER), 9) "
                f"AS bucket, s.lo, s.w\n       FROM data, s WHERE {x} IS NOT NULL)\n"
                f"SELECT bucket, ROUND(MIN(lo + bucket * w), 2) AS from_value,\n"
                f"       ROUND(MIN(lo + (bucket + 1) * w), 2) AS to_value, COUNT(*) AS rows\n"
                f"FROM b\nGROUP BY bucket\nORDER BY bucket",
                {"column": _label(p.numbers[0])},
                ["CTE", "histogram"],
            )
        )

    # 5. Category × numeric comparison, top and bottom segments.
    if p.categories and p.numbers:
        c, n = p.categories[0], p.numbers[0]
        out.append(
            Question(
                f"compare_{n.name}_by_{c.name}",
                "category_numeric",
                f"SELECT {q(c.name)}, COUNT(*) AS rows,\n"
                f"       ROUND(AVG({q(n.name)}), 2) AS average,\n"
                f"       ROUND(MEDIAN({q(n.name)}), 2) AS median,\n"
                f"       ROUND(SUM({q(n.name)}), 2) AS total\n"
                f"FROM data\nGROUP BY 1\nORDER BY total DESC NULLS LAST\nLIMIT 20",
                {"column": _label(c), "metric": _label(n)},
                ["GROUP BY", "AVG", "SUM"],
            )
        )
        group = [c] + p.categories[1:2]
        keys = ", ".join(q(g.name) for g in group)
        for direction in ("top", "bottom"):
            out.append(
                Question(
                    f"{direction}_segments",
                    f"{direction}_segments",
                    f"SELECT {keys}, COUNT(*) AS rows, ROUND(SUM({q(n.name)}), 2) AS total\n"
                    f"FROM data\nGROUP BY ALL\nHAVING COUNT(*) >= 3\n"
                    f"ORDER BY total {'DESC' if direction == 'top' else 'ASC'} NULLS LAST\nLIMIT 10",
                    {"columns": ", ".join(_label(g) for g in group), "metric": _label(n)},
                    ["GROUP BY ALL", "HAVING"],
                )
            )
    elif len(labels) >= 2:
        a, b = labels[0], labels[1]
        out.append(
            Question(
                f"cross_{a.name}_{b.name}",
                "category_cross",
                f"SELECT {q(a.name)}, {q(b.name)}, COUNT(*) AS rows\n"
                f"FROM data\nGROUP BY 1, 2\nORDER BY rows DESC\nLIMIT 20",
                {"column": _label(a), "other": _label(b)},
                ["GROUP BY"],
            )
        )

    # 6. Time trend.
    if p.dates:
        d = p.dates[0]
        grain = _grain(d)
        metric = (
            f",\n       ROUND(SUM({q(p.numbers[0].name)}), 2) AS total_{p.numbers[0].name}"
            if p.numbers
            else ""
        )
        out.append(
            Question(
                f"trend_{d.name}",
                "time_trend",
                f"SELECT date_trunc('{grain}', {q(d.name)}) AS period, COUNT(*) AS rows{metric}\n"
                f"FROM data\nWHERE {q(d.name)} IS NOT NULL\nGROUP BY 1\nORDER BY 1",
                {
                    "date": _label(d),
                    "grain": grain,
                    "metric": _label(p.numbers[0]) if p.numbers else "",
                },
                ["date_trunc", "time series"],
            )
        )

    # 7. Outliers (1.5 × IQR) of the main quantities.
    if p.numbers:
        parts = []
        for m in p.numbers[:4]:
            x = q(m.name)
            parts.append(
                f"SELECT {lit(m.source)} AS column_name, COUNT(*) FILTER (WHERE {x} < q1 - 1.5 * (q3 - q1)"
                f" OR {x} > q3 + 1.5 * (q3 - q1)) AS outliers,\n"
                f"       ROUND(q1 - 1.5 * (q3 - q1), 2) AS low_limit, ROUND(q3 + 1.5 * (q3 - q1), 2) AS high_limit\n"
                f"FROM data, (SELECT quantile_cont({x}, 0.25) AS q1, quantile_cont({x}, 0.75) AS q3 FROM data)\n"
                f"GROUP BY q1, q3"
            )
        out.append(
            Question(
                "outliers",
                "outliers",
                "\nUNION ALL\n".join(parts) + "\nORDER BY outliers DESC",
                {"columns": ", ".join(_label(m) for m in p.numbers[:4])},
                ["IQR", "FILTER"],
            )
        )

    # 8. Correlations between quantities.
    if len(p.numbers) >= 2:
        cols = p.numbers[:6]
        parts = [
            f"SELECT {lit(a.source)} AS column_a, {lit(b.source)} AS column_b, "
            f"ROUND(CORR({q(a.name)}, {q(b.name)}), 3) AS correlation FROM data"
            for i, a in enumerate(cols)
            for b in cols[i + 1 :]
        ]
        out.append(
            Question(
                "correlations",
                "correlations",
                "\nUNION ALL\n".join(parts) + "\nORDER BY ABS(correlation) DESC NULLS LAST",
                {"columns": ", ".join(_label(m) for m in cols)},
                ["CORR"],
            )
        )

    # 9. Identifiers: are they unique?
    ids = [m for m in metas if m.kind == "identifier"][:1]
    for m in ids:
        out.append(
            Question(
                f"duplicates_{m.name}",
                "identifier_duplicates",
                f"SELECT COUNT({q(m.name)}) AS filled, COUNT(DISTINCT {q(m.name)}) AS distinct_values,\n"
                f"       COUNT({q(m.name)}) - COUNT(DISTINCT {q(m.name)}) AS repeated,\n"
                f"       (SELECT ARG_MAX({q(m.name)}, n) FROM (SELECT {q(m.name)}, COUNT(*) AS n FROM data\n"
                f"         WHERE {q(m.name)} IS NOT NULL GROUP BY 1 HAVING COUNT(*) > 1)) AS most_repeated\n"
                f"FROM data",
                {"column": _label(m)},
                ["HAVING"],
            )
        )
    return out[:MAX_QUESTIONS]


def _grain(meta: ColumnMeta) -> str:
    """Month for spans over ~3 months, day for shorter ones, year for decades."""
    from datetime import date

    try:
        lo, hi = date.fromisoformat(str(meta.min)[:10]), date.fromisoformat(str(meta.max)[:10])
    except ValueError:
        return "month"
    days = (hi - lo).days
    if days > 365 * 8:
        return "year"
    if days > 90:
        return "month"
    return "day"
