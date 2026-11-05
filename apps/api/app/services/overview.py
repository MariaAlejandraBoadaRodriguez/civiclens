"""Dashboard for any table: KPI tiles, quality before → after, and sections that each pair a
small dataset for a chart with a written finding (EN/ES).

Sections (each only when the table has what it needs, so nothing is ever empty):
distribution of the main quantity, most common values of the main category, top segments,
drivers (target rate by category, else the strongest correlation), trend over time, unusual
values (IQR) and what the prediction model relies on (when it was trained).

Every number comes from SQL on the table ``data`` through the read-only engine; the SQL is
returned with each section so the dashboard can show it. A custom chart (metric, aggregation,
dimension, filters) is built from validated column names only.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core import packs
from app.core.analysis.questions import lit, pick, positive_expr, q
from app.core.analysis.table import NUMERIC_KINDS, TEMPORAL_KINDS, ColumnMeta
from app.core.reports import format as fmt
from app.core.sql import engine
from app.core.sql.guard import QueryRejected
from app.db.models import Dataset
from app.i18n.loader import Translator
from app.services import analysis, storage

log = logging.getLogger(__name__)
TOP = 10
BINS = 12
# How each section's values read: rows, a quantity, a rate (0–1) or a correlation.
UNITS = {
    "distribution": "count",
    "counts": "count",
    "counts_2": "count",
    "segments": "amount",
    "drivers": "ratio",
    "trend": "amount",
    "outliers": "count",
    "model": "ratio",
}


def _run(ds: Dataset, sql: str) -> list[list[Any]]:
    return engine.run(storage.star_path(ds.id), sql, timeout_s=10).rows


def _num(value: Any, lang: str) -> str:
    if value is None:
        return "—"
    v = float(value)
    return (
        fmt.compact(v, lang) if abs(v) >= 10_000 else fmt.number(v, lang, 0 if v == int(v) else 2)
    )


def _label(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value)


def _section(
    sid: str,
    chart: str,
    sql: str,
    rows: list[dict[str, Any]],
    title: str,
    finding: str,
    x: str = "",
    y: str = "",
) -> dict[str, Any]:
    return {
        "id": sid,
        "chart": chart,
        "title": title,
        "finding": finding,
        "x_label": x,
        "y_label": y,
        "rows": rows,
        "sql": sql,
    }


# --------------------------------------------------------------------------- sections


def distribution(ds, m: ColumnMeta, t: Translator) -> dict[str, Any] | None:
    x = q(m.name)
    sql = (
        f"WITH s AS (SELECT MIN({x}) AS lo, (MAX({x}) - MIN({x})) / {BINS}.0 AS w FROM data),\n"
        f"b AS (SELECT LEAST(CAST(FLOOR(({x} - s.lo) / NULLIF(s.w, 0)) AS INTEGER), {BINS - 1}) "
        f"AS bucket, s.lo, s.w FROM data, s WHERE {x} IS NOT NULL)\n"
        f"SELECT bucket, MIN(lo + bucket * w) AS from_value, MIN(lo + (bucket + 1) * w) AS to_value,"
        f" COUNT(*) AS rows FROM b GROUP BY bucket ORDER BY bucket"
    )
    data = _run(ds, sql)
    median = _run(ds, f"SELECT MEDIAN({x}) FROM data")[0][0]  # noqa: S608
    if not data:
        return None
    rows = [
        {
            "label": f"{_num(lo, t.lang)}–{_num(hi, t.lang)}",
            "value": n,
            "from": float(lo),
            "to": float(hi),
        }
        for _, lo, hi, n in data
    ]
    peak = max(data, key=lambda r: r[3])
    total = sum(r[3] for r in data) or 1
    finding = t(
        "dashboard_any.findings.distribution",
        column=m.source,
        low=_num(peak[1], t.lang),
        high=_num(peak[2], t.lang),
        share=fmt.percent(peak[3] / total, t.lang, 0),
        median=_num(median, t.lang),
    )
    return _section(
        "distribution",
        "histogram",
        sql,
        rows,
        t("dashboard_any.sections.distribution", column=m.source),
        finding,
        m.source,
        t("dashboard_any.rows"),
    )


def counts(ds, m: ColumnMeta, t: Translator, sid: str = "counts") -> dict[str, Any] | None:
    x = q(m.name)
    sql = (
        f"SELECT {x} AS value, COUNT(*) AS rows, COUNT(*) / SUM(COUNT(*)) OVER () AS share "
        f"FROM data WHERE {x} IS NOT NULL GROUP BY 1 ORDER BY rows DESC LIMIT {TOP}"
    )
    data = _run(ds, sql)
    if not data:
        return None
    rows = [{"label": _label(v), "value": n, "share": round(float(s), 4)} for v, n, s in data]
    finding = t(
        "dashboard_any.findings.counts",
        column=m.source,
        value=rows[0]["label"],
        share=fmt.percent(rows[0]["share"], t.lang, 0),
        n=len(rows),
    )
    return _section(
        sid,
        "bar",
        sql,
        rows,
        t("dashboard_any.sections.counts", column=m.source),
        finding,
        m.source,
        t("dashboard_any.rows"),
    )


def segments(ds, c: ColumnMeta, n: ColumnMeta, t: Translator) -> dict[str, Any] | None:
    sql = (
        f"SELECT {q(c.name)} AS value, SUM({q(n.name)}) AS total, COUNT(*) AS rows, "
        f"SUM({q(n.name)}) / SUM(SUM({q(n.name)})) OVER () AS share FROM data "
        f"WHERE {q(c.name)} IS NOT NULL GROUP BY 1 ORDER BY total DESC NULLS LAST LIMIT {TOP}"
    )
    data = _run(ds, sql)
    if not data or data[0][1] is None:
        return None
    rows = [
        {
            "label": _label(v),
            "value": float(s or 0),
            "rows": r,
            "share": None if sh is None else round(float(sh), 4),
        }
        for v, s, r, sh in data
    ]
    finding = t(
        "dashboard_any.findings.segments",
        column=c.source,
        metric=n.source,
        value=rows[0]["label"],
        share=fmt.percent(rows[0]["share"] or 0, t.lang, 0),
    )
    return _section(
        "segments",
        "bar",
        sql,
        rows,
        t("dashboard_any.sections.segments", column=c.source, metric=n.source),
        finding,
        c.source,
        n.source,
    )


def target_drivers(
    ds, target: ColumnMeta, c: ColumnMeta, positive: str | None, t: Translator
) -> dict[str, Any] | None:
    pos = positive_expr(target, positive)
    sql = (
        f"SELECT {q(c.name)} AS value, COUNT(*) AS rows, "
        f"AVG(CASE WHEN {pos} THEN 1.0 ELSE 0.0 END) AS rate FROM data "
        f"WHERE {q(c.name)} IS NOT NULL AND {q(target.name)} IS NOT NULL "
        f"GROUP BY 1 HAVING COUNT(*) >= 20 ORDER BY rate DESC LIMIT {TOP}"
    )
    overall_sql = (
        f"SELECT AVG(CASE WHEN {pos} THEN 1.0 ELSE 0.0 END) FROM data "  # noqa: S608
        f"WHERE {q(target.name)} IS NOT NULL"
    )
    data = _run(ds, sql)
    overall = _run(ds, overall_sql)[0][0]
    if not data or overall is None:
        return None
    rows = [{"label": _label(v), "value": round(float(r), 4), "rows": n} for v, n, r in data]
    finding = t(
        "dashboard_any.findings.drivers",
        column=c.source,
        target=target.source,
        value=rows[0]["label"],
        rate=fmt.percent(rows[0]["value"], t.lang, 1),
        overall=fmt.percent(float(overall), t.lang, 1),
    )
    return _section(
        "drivers",
        "bar",
        sql,
        rows,
        t("dashboard_any.sections.drivers", column=c.source, target=target.source),
        finding,
        c.source,
        t("dashboard_any.rate", target=target.source),
    )


def correlations(ds, nums: list[ColumnMeta], t: Translator) -> dict[str, Any] | None:
    pairs = [(a, b) for i, a in enumerate(nums[:6]) for b in nums[i + 1 : 6]]
    if not pairs:
        return None
    sql = (
        "\nUNION ALL\n".join(
            f"SELECT {lit(a.source)} AS a, {lit(b.source)} AS b, CORR({q(a.name)}, {q(b.name)}) AS r "
            f"FROM data"
            for a, b in pairs
        )
        + "\nORDER BY ABS(r) DESC NULLS LAST"
    )
    data = [r for r in _run(ds, sql) if r[2] is not None]
    if not data:
        return None
    rows = [{"label": f"{a} × {b}", "value": round(float(r), 3)} for a, b, r in data[:TOP]]
    a, b, r = data[0]
    finding = t(
        "dashboard_any.findings.correlation",
        a=a,
        b=b,
        r=fmt.number(float(r), t.lang, 2),
        direction=t(f"dashboard_any.{'together' if r > 0 else 'opposite'}"),
    )
    return _section(
        "drivers", "bar", sql, rows, t("dashboard_any.sections.correlations"), finding, "", "r"
    )


def _grain(meta: ColumnMeta) -> str:
    from app.core.analysis.questions import _grain as grain

    return grain(meta)


def trend(ds, d: ColumnMeta, n: ColumnMeta | None, t: Translator) -> dict[str, Any] | None:
    grain = _grain(d)
    value = f"SUM({q(n.name)})" if n is not None else "COUNT(*)"
    fmt_str = {"year": "%Y", "month": "%Y-%m", "day": "%Y-%m-%d"}[grain]
    sql = (
        f"SELECT strftime(date_trunc('{grain}', {q(d.name)}), '{fmt_str}') AS period, "
        f"{value} AS value FROM data WHERE {q(d.name)} IS NOT NULL GROUP BY 1 ORDER BY 1"
    )
    data = [r for r in _run(ds, sql) if r[1] is not None]
    if len(data) < 2:
        return None
    rows = [{"label": p, "value": float(v)} for p, v in data[-60:]]
    peak = max(rows, key=lambda r: r["value"])
    first, last = rows[0]["value"], rows[-1]["value"]
    change = (last / first - 1) if first else None
    metric = n.source if n is not None else t("dashboard_any.rows")
    finding = t(
        "dashboard_any.findings.trend",
        metric=metric,
        grain=t(f"analysis.grain.{grain}"),
        peak=peak["label"],
        value=_num(peak["value"], t.lang),
        first=rows[0]["label"],
        last=rows[-1]["label"],
        change="—" if change is None else fmt.percent(change, t.lang, 0),
    )
    return _section(
        "trend",
        "line",
        sql,
        rows,
        t("dashboard_any.sections.trend", metric=metric, date=d.source),
        finding,
        d.source,
        metric,
    )


def outliers(ds, nums: list[ColumnMeta], t: Translator) -> dict[str, Any] | None:
    parts = []
    for m in nums[:6]:
        x = q(m.name)
        parts.append(
            f"SELECT {lit(m.source)} AS column_name, COUNT(*) FILTER (WHERE {x} < q1 - 1.5 * (q3 - q1)"
            f" OR {x} > q3 + 1.5 * (q3 - q1)) AS outliers, COUNT({x}) AS filled FROM data, "
            f"(SELECT quantile_cont({x}, 0.25) AS q1, quantile_cont({x}, 0.75) AS q3 FROM data) "
            f"GROUP BY q1, q3"
        )
    if not parts:
        return None
    sql = "\nUNION ALL\n".join(parts) + "\nORDER BY outliers DESC"
    data = _run(ds, sql)
    rows = [
        {"label": c, "value": int(o), "share": round(o / f, 4) if f else 0.0} for c, o, f in data
    ]
    top = rows[0]
    key = "outliers" if top["value"] else "no_outliers"
    finding = t(
        f"dashboard_any.findings.{key}",
        column=top["label"],
        n=fmt.number(top["value"], t.lang),
        share=fmt.percent(top["share"], t.lang, 1),
    )
    return _section(
        "outliers",
        "bar",
        sql,
        rows,
        t("dashboard_any.sections.outliers"),
        finding,
        "",
        t("dashboard_any.rows"),
    )


def model_section(ds, t: Translator) -> dict[str, Any] | None:
    from app.services import ml

    result = ml.load_result(ds, "target_model") or {}
    if result.get("status") != "ok":
        return None
    headers = {m.name: m.source for m in analysis.columns(ds)}
    rows = [
        {"label": headers.get(r["feature"], r["feature"]), "value": r["share"]}
        for r in result["importance"][:8]
    ]
    if not rows:
        return None
    target = headers.get(result["target"], result["target"])
    finding = t(
        "dashboard_any.findings.model",
        target=target,
        column=rows[0]["label"],
        share=fmt.percent(rows[0]["value"], t.lang, 0),
    )
    if result.get("leakage"):
        finding += " " + t(
            "dashboard_any.findings.model_leak",
            columns=", ".join(
                headers.get(lk["feature"], lk["feature"]) for lk in result["leakage"]
            ),
        )
    return _section(
        "model",
        "bar",
        "",
        rows,
        t("dashboard_any.sections.model", target=target),
        finding,
        "",
        t("dashboard_any.share"),
    )


# --------------------------------------------------------------------------- overview


def kpi_tiles(ds: Dataset, t: Translator) -> list[dict[str, Any]]:
    """Pack KPIs in the pack layout's order, then the table's own KPIs (at most 8)."""
    d = analysis.domain(ds)
    layout = packs.packs()[d["pack"]].layout.get("kpis", [])
    pack_items = analysis.pack_kpis(ds, t)
    order = {f"{d['pack']}.{k}": i for i, k in enumerate(layout)}
    pack_items.sort(key=lambda k: order.get(k["kpi_id"], len(order)))
    return (pack_items + analysis.generic_kpis(ds, t))[:8]


def overview(ds: Dataset, t: Translator) -> dict[str, Any]:
    from app.services import sql as sql_svc

    sql_svc.ensure_star(ds)
    metas = analysis.columns(ds)
    p = pick(metas)
    d = analysis.domain(ds)
    by_name = {m.name: m for m in metas}
    target, positive = p.target, None
    for objective in packs.packs()[d["pack"]].ml:
        entry = d["roles"].get(objective.get("target_role") or "")
        if entry and entry.get("column") in by_name:
            target, positive = by_name[entry["column"]], entry.get("positive")
    labels = p.categories + [
        m for m in metas if m.kind == "category" and m not in p.categories and m.distinct >= 2
    ]
    labels = [m for m in labels if target is None or m.name != target.name]
    nums = p.numbers
    builders = []
    if nums:
        builders.append(lambda: distribution(ds, nums[0], t))
    if labels:
        builders.append(lambda: counts(ds, labels[0], t))
    if len(labels) > 1 and not nums:  # mostly-text tables: a second category instead
        builders.append(lambda: counts(ds, labels[1], t, sid="counts_2"))
    if labels and nums:
        builders.append(lambda: segments(ds, labels[0], nums[0], t))
    if target is not None and labels:
        builders.append(lambda: target_drivers(ds, target, labels[0], positive, t))
    elif len(nums) >= 2:
        builders.append(lambda: correlations(ds, nums, t))
    if p.dates:
        builders.append(lambda: trend(ds, p.dates[0], nums[0] if nums else None, t))
    if nums:
        builders.append(lambda: outliers(ds, nums, t))
    builders.append(lambda: model_section(ds, t))
    sections = []
    for build in builders:
        try:
            section = build()
        except (QueryRejected, ZeroDivisionError, ValueError) as exc:
            log.warning("overview section skipped for %s: %s", ds.id, exc)
            continue
        if section is not None:
            section["unit"] = UNITS.get(section["id"], "count")
            if section["id"] == "drivers" and section["y_label"] == "r":
                section["unit"] = "r"
            sections.append(section)
    profile = ds.profile_json or {}
    after = (profile.get("quality_after") or {}).get("score")
    return {
        "dataset_id": str(ds.id),
        "origin": sql_svc.star_origin(ds),
        "domain": {"pack": d["pack"], "goal": d["goal"], "name": t(f"packs.{d['pack']}.name")},
        "rows": metas[0].rows if metas else 0,
        "columns": len(metas),
        "quality": {"before": ds.quality_score, "after": after},
        "kpis": kpi_tiles(ds, t),
        "sections": sections,
        "dimensions": [
            {"name": m.name, "source": m.source, "kind": m.kind}
            for m in metas
            if m.kind in ("category", "boolean")
            or m.kind in TEMPORAL_KINDS
            or (m.kind == "identifier" and m.distinct <= 500)
        ],
        "metrics": [{"name": m.name, "source": m.source} for m in metas if m.kind in NUMERIC_KINDS],
    }


# --------------------------------------------------------------------------- custom chart

AGGREGATIONS = {
    "count": "COUNT(*)",
    "sum": "SUM({x})",
    "avg": "AVG({x})",
    "median": "MEDIAN({x})",
    "min": "MIN({x})",
    "max": "MAX({x})",
}
OPS = {"eq": "=", "ne": "<>", "gte": ">=", "lte": "<="}


class ChartError(ValueError):
    def __init__(self, code: str, **params: Any) -> None:
        super().__init__(code)
        self.code, self.params = code, params


def chart(ds: Dataset, spec: dict[str, Any]) -> dict[str, Any]:
    """A chart the user configures. Column names are checked against the table; values are
    escaped literals; the result is capped at 50 groups."""
    metas = {m.name: m for m in analysis.columns(ds)}

    def column(name: str | None, field: str) -> ColumnMeta:
        if name not in metas:
            raise ChartError("chart.unknown_column", field=field, column=str(name))
        return metas[name]

    agg = spec.get("aggregation", "count")
    if agg not in AGGREGATIONS:
        raise ChartError("chart.unknown_aggregation", aggregation=agg)
    if agg == "count":
        value = "COUNT(*)"
    else:
        metric = column(spec.get("metric"), "metric")
        if metric.kind not in NUMERIC_KINDS:
            raise ChartError("chart.metric_not_numeric", column=metric.source)
        value = AGGREGATIONS[agg].format(x=q(metric.name))
    dim = column(spec.get("dimension"), "dimension")
    if dim.kind in TEMPORAL_KINDS:
        grain = spec.get("grain") or _grain(dim)
        if grain not in ("year", "month", "day"):
            raise ChartError("chart.unknown_grain", grain=str(grain))
        fmt_str = {"year": "%Y", "month": "%Y-%m", "day": "%Y-%m-%d"}[grain]
        group = f"strftime(date_trunc('{grain}', {q(dim.name)}), '{fmt_str}')"
        order = "1"
    else:
        group, order = q(dim.name), "2 DESC NULLS LAST"
    where = [f"{q(dim.name)} IS NOT NULL"]
    for f in spec.get("filters", [])[:5]:
        col = column(f.get("column"), "filters")
        op, values = f.get("op", "eq"), f.get("values") or []
        if not values:
            continue
        text = f"CAST({q(col.name)} AS VARCHAR)"
        if op == "in":
            where.append(f"{text} IN ({', '.join(lit(str(v)) for v in values[:50])})")
        elif op in OPS:
            if col.kind in NUMERIC_KINDS:
                try:
                    number = float(values[0])
                except (TypeError, ValueError) as exc:
                    raise ChartError("chart.bad_filter", column=col.source) from exc
                where.append(f"{q(col.name)} {OPS[op]} {number!r}")
            else:
                where.append(f"{text} {OPS[op]} {lit(str(values[0]))}")
        else:
            raise ChartError("chart.bad_filter", column=col.source)
    sql = (
        f"SELECT {group} AS label, {value} AS value FROM data WHERE {' AND '.join(where)} "
        f"GROUP BY 1 ORDER BY {order} LIMIT 50"
    )
    result = engine.run(storage.star_path(ds.id), sql, timeout_s=10)
    rows = [
        {"label": _label(r[0]), "value": None if r[1] is None else float(r[1])} for r in result.rows
    ]
    return {
        "sql": sql,
        "chart": spec.get("chart_type", "bar"),
        "rows": rows,
        "dimension": dim.source,
        "aggregation": agg,
        "metric": None if agg == "count" else metas[spec["metric"]].source,
    }
