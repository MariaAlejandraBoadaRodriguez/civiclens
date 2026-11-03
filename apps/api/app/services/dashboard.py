"""Executive dashboard (spec M5): KPIs, monthly spend and a cross-jurisdiction comparison in
CAD, for one dataset or several, with period and category filters.

The selected datasets' star schemas are attached read-only to one in-memory DuckDB connection
and queried together, so combined KPIs (HHI over every supplier, a combined median) are exact,
not averages of averages. Nothing is materialized: the fact tables are a few MB.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

import duckdb

from app.core.sql.star_schema import GROUPS
from app.db.models import Dataset
from app.i18n.loader import Translator
from app.services import ml, sql
from app.services.reports import PEAK_RATIO

Period = Literal["all", "12m", "fy"]
Category = Literal["all", "goods", "services", "construction", "other"]
MONTHS_ALL = 24  # the "all" view charts the last 24 months
FY_MIN_SHARE = 0.1  # a fiscal year counts as "last" once it holds 10 % of the contracts
# HHI on a 0–1 scale (US DOJ/FTC guidelines, 2023: 1,000 and 1,800 on the 0–10,000 scale).
HHI_LEVELS = ((0.10, "unconcentrated"), (0.18, "moderate"), (1.01, "high"))


@dataclass(frozen=True)
class Window:
    """One dataset's current and previous period as half-open ``[start, end)`` month ranges;
    ``None`` bounds mean "no limit" (period ``all``)."""

    start: date | None
    end: date | None
    prev_start: date | None
    prev_end: date | None
    fiscal_year: int | None = None


def _add_months(d: date, n: int) -> date:
    y, m = divmod(d.year * 12 + d.month - 1 + n, 12)
    return date(y, m + 1, 1)


def _window(con: duckdb.DuckDBPyConnection, alias: str, period: Period) -> Window:
    if period == "all":
        return Window(None, None, None, None)
    if period == "12m":
        last = con.execute(
            f"SELECT MAX(d.month_start) FROM {alias}.fact_contract f "  # noqa: S608 — fixed alias
            f"JOIN {alias}.dim_date d USING (date_id)"
        ).fetchone()[0]
        if last is None:
            return Window(None, None, None, None)
        end = _add_months(last, 1)
        start = _add_months(end, -12)
        return Window(start, end, _add_months(start, -12), start)
    rows = con.execute(
        f"SELECT d.fiscal_year, MIN(d.month_start), MAX(d.month_start), COUNT(*) "  # noqa: S608
        f"FROM {alias}.fact_contract f JOIN {alias}.dim_date d USING (date_id) "
        "GROUP BY 1 ORDER BY 1"
    ).fetchall()
    total = sum(r[3] for r in rows)
    big = [r for r in rows if r[3] >= FY_MIN_SHARE * total]
    if not big:
        return Window(None, None, None, None)
    fy, first, last, _ = big[-1]
    prev = next((r for r in rows if r[0] == fy - 1), None)
    return Window(
        first,
        _add_months(last, 1),
        prev[1] if prev else None,
        _add_months(prev[2], 1) if prev else first,
        fiscal_year=int(fy),
    )


def _between(col: str, start: date | None, end: date | None) -> str:
    if start is None and end is None:
        return "TRUE"
    parts = []
    if start is not None:
        parts.append(f"{col} >= DATE '{start.isoformat()}'")
    if end is not None:
        parts.append(f"{col} < DATE '{end.isoformat()}'")
    return " AND ".join(parts)


def _base_sql(aliases: list[str], windows: list[Window], category: Category) -> str:
    """One row per contract of every selected dataset, tagged with its window membership."""
    selects = []
    for i, (alias, w) in enumerate(zip(aliases, windows, strict=True)):
        has_prev = w.prev_start is not None or w.prev_end is not None
        selects.append(
            # Only integers, fixed aliases and date literals from ``date`` objects go in here.
            f"SELECT {i} AS ds, f.amount_cad, f.award_type, '{i}:' || f.supplier_id AS supplier, "  # noqa: S608
            f"f.category_id AS category, d.month_start, "
            f"({_between('d.month_start', w.start, w.end)}) AS cur, "
            f"({_between('d.month_start', w.prev_start, w.prev_end) if has_prev else 'FALSE'}) "
            f"AS prev "
            f"FROM {alias}.fact_contract f LEFT JOIN {alias}.dim_date d USING (date_id)"
        )
    if category != "all" and category not in GROUPS:  # the API validates it; never trust it here
        raise ValueError(category)
    where = "" if category == "all" else f" WHERE category = '{category}'"
    return f"SELECT * FROM ({' UNION ALL '.join(selects)}){where}"  # noqa: S608 — see above


AGG = """
SELECT
  SUM(amount_cad), COUNT(*), AVG(amount_cad), MEDIAN(amount_cad),
  COUNT(*) FILTER (WHERE award_type = 'direct') / NULLIF(COUNT(award_type), 0),
  COUNT(*) FILTER (WHERE amount_cad IS NULL)
FROM base WHERE {flag}
"""
HHI = """
SELECT SUM(share * share) FROM (
  SELECT SUM(amount_cad) / SUM(SUM(amount_cad)) OVER () AS share
  FROM base WHERE cur AND amount_cad > 0 GROUP BY supplier)
"""
MONTHLY = """
SELECT strftime(month_start, '%Y-%m') AS month, SUM(amount_cad), COUNT(*)
FROM base WHERE cur AND month_start IS NOT NULL AND amount_cad IS NOT NULL
GROUP BY 1 ORDER BY 1
"""
BY_DATASET = """
SELECT ds, SUM(amount_cad), COUNT(*), COUNT(*) FILTER (WHERE amount_cad IS NULL)
FROM base WHERE cur GROUP BY ds
"""


def _num(value: Any, digits: int = 6) -> float | None:
    return None if value is None else round(float(value), digits)


def _hhi_level(value: float | None) -> str | None:
    if value is None:
        return None
    return next(level for limit, level in HHI_LEVELS if value < limit)


def _quality(datasets: list[Dataset], counts: list[int]) -> tuple[float | None, float | None]:
    """Contract-weighted quality score before and after cleaning."""
    before = after = weight_b = weight_a = 0.0
    for ds, n in zip(datasets, counts, strict=True):
        if ds.quality_score is not None:
            before += ds.quality_score * n
            weight_b += n
        q_after = ((ds.profile_json or {}).get("quality_after") or {}).get("score")
        score = q_after if q_after is not None and sql.star_origin(ds) == "clean" else None
        if score is not None:
            after += score * n
            weight_a += n
    b = round(before / weight_b, 1) if weight_b else None
    a = round(after / weight_a, 1) if weight_a else None
    return b, a


def _flagged_in(datasets: list[Dataset], month: str) -> int | None:
    """Red-flagged contracts signed in ``month`` (None when the model has not run anywhere)."""
    total, ran = 0, False
    for ds in datasets:
        result = ml.load_result(ds, "red_flags")
        if not result or result.get("model_type") != "red_flags":
            continue
        ran = True
        total += sum(
            1 for i in result.get("items", []) if str(i.get("signed_date", ""))[:7] == month
        )
    return total if ran else None


def build(
    datasets: list[Dataset], t: Translator, period: Period = "all", category: Category = "all"
) -> dict[str, Any]:
    paths = [sql.ensure_star(ds) for ds in datasets]
    aliases = [f"d{i}" for i in range(len(datasets))]
    con = duckdb.connect(":memory:", config={"autoinstall_known_extensions": False})
    try:
        con.execute("SET threads = 2")
        con.execute("SET memory_limit = '256MB'")
        for alias, path in zip(aliases, paths, strict=True):
            con.execute(f"ATTACH '{path.as_posix()}' AS {alias} (READ_ONLY)")
        con.execute("SET enable_external_access = false")
        windows = [_window(con, alias, period) for alias in aliases]
        con.execute(f"CREATE TEMP VIEW base AS {_base_sql(aliases, windows, category)}")
        cur = con.execute(AGG.format(flag="cur")).fetchone()
        prev = con.execute(AGG.format(flag="prev")).fetchone()
        hhi = con.execute(HHI).fetchone()[0]
        monthly_rows = con.execute(MONTHLY).fetchall()
        per_ds = {r[0]: r for r in con.execute(BY_DATASET).fetchall()}
    finally:
        con.close()

    counts = [int(per_ds[i][2]) if i in per_ds else 0 for i in range(len(datasets))]
    q_before, q_after = _quality(datasets, counts)
    has_prev = period != "all" and bool(prev[1])

    def delta(i: int) -> float | None:
        if not has_prev or cur[i] is None or not prev[i]:
            return None
        return round(float(cur[i]) / float(prev[i]) - 1, 4)

    def kpi(kpi_id: str, value: Any, unit: str, **extra: Any) -> dict[str, Any]:
        return {
            "kpi_id": kpi_id,
            "value": _num(value),
            "unit": unit,
            "currency": "CAD" if unit == "currency" else None,
            "name": t(f"kpi_catalog.{kpi_id}.name"),
            "definition": t(f"kpi_catalog.{kpi_id}.definition"),
            **extra,
        }

    direct_delta = (
        round(float(cur[4]) - float(prev[4]), 4)
        if has_prev and cur[4] is not None and prev[4] is not None
        else None
    )
    level = _hhi_level(_num(hhi))
    kpis = [
        kpi("total_spend", cur[0], "currency", change=delta(0)),
        kpi("contract_count", cur[1], "count", change=delta(1)),
        kpi("avg_value", cur[2], "currency", median=_num(cur[3], 2)),
        kpi("direct_award_share", cur[4], "ratio", change_points=direct_delta),
        kpi(
            "hhi",
            hhi,
            "index",
            level=level,
            level_label=t(f"dashboard.hhi.{level}") if level else None,
        ),
        kpi(
            "quality_score", q_after if q_after is not None else q_before, "score", before=q_before
        ),
    ]

    monthly = [
        {"month": m, "spend": round(float(s), 2), "contracts": int(n)} for m, s, n in monthly_rows
    ]
    if period == "all":
        monthly = monthly[-MONTHS_ALL:]
    peak = None
    finding = t("dashboard.finding.empty")
    if monthly:
        mean = sum(m["spend"] for m in monthly) / len(monthly)
        top = max(monthly, key=lambda m: m["spend"])
        ratio = round(top["spend"] / mean, 2) if mean else 0.0
        flagged = _flagged_in(datasets, top["month"])
        peak = {**top, "ratio": ratio, "is_peak": ratio >= PEAK_RATIO, "flagged": flagged}
        from app.core.reports import format as fmt

        month_text = fmt.month(top["month"], t.lang)
        if peak["is_peak"]:
            finding = t(
                "dashboard.finding.peak", month=month_text, ratio=fmt.number(ratio, t.lang, 1)
            )
        else:
            finding = t(
                "dashboard.finding.flat", month=month_text, ratio=fmt.number(ratio, t.lang, 1)
            )
        if flagged:
            finding += " " + t("dashboard.finding.flagged", n=flagged, month=month_text)

    by_jurisdiction = []
    top_spend = max((float(per_ds[i][1] or 0) for i in per_ds), default=0) or 1
    for i, ds in enumerate(datasets):
        row = per_ds.get(i)
        spend = float(row[1] or 0) if row else 0.0
        w = windows[i]
        by_jurisdiction.append(
            {
                "dataset_id": str(ds.id),
                "slug": ds.slug,
                "jurisdiction": sql.jurisdiction(ds),
                "name": _dataset_name(ds, t),
                "label": t(f"dashboard.jurisdictions.{sql.jurisdiction(ds)}")
                if ds.slug
                else _dataset_name(ds, t),
                "spend": round(spend, 2),
                "contracts": int(row[2]) if row else 0,
                "share_of_max": round(spend / top_spend, 4),
                "origin": sql.star_origin(ds),
                "window": {
                    "start": w.start.isoformat()[:7] if w.start else None,
                    "end": _add_months(w.end, -1).isoformat()[:7] if w.end else None,
                    "fiscal_year": w.fiscal_year,
                },
            }
        )
    return {
        "filters": {"period": period, "category": category},
        "currency": "CAD",
        "kpis": kpis,
        "monthly": monthly,
        "peak": peak,
        "finding": finding,
        "by_jurisdiction": by_jurisdiction,
        "notes": _notes(datasets, per_ds, t),
    }


def _dataset_name(ds: Dataset, t: Translator) -> str:
    from app.core.seed.registry import SEEDS

    return t(f"datasets.{ds.slug}.name") if ds.slug in SEEDS else ds.name


def _notes(datasets: list[Dataset], per_ds: dict[int, Any], t: Translator) -> list[str]:
    from app.core.reports import format as fmt
    from app.services.cleaning import context, default_currency

    notes = []
    for i, ds in enumerate(datasets):
        label = (
            t(f"dashboard.jurisdictions.{sql.jurisdiction(ds)}")
            if ds.slug
            else _dataset_name(ds, t)
        )
        currency = default_currency(ds)
        if currency and currency != "CAD":
            source = context().fx.sources.get(currency, "")
            notes.append(t("dashboard.notes.fx", place=label, currency=currency, source=source))
        row = per_ds.get(i)
        if row and row[2] and row[3]:
            share = row[3] / row[2]
            notes.append(
                t("dashboard.notes.missing", place=label, share=fmt.percent(share, t.lang))
            )
        if sql.star_origin(ds) != "clean":
            notes.append(t("dashboard.notes.recommended", place=label))
    notes.append(t("dashboard.notes.flags"))
    return notes
