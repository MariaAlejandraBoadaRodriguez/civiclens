"""Executive summary of a dataset (shared by the report and the dashboard) and the HTML report.

Everything here reads the star schema and stored model results; nothing heavy runs at request
time. Machine values stay as they are; only texts and number formats follow the language.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.reports import format as fmt
from app.core.seed.registry import SEEDS
from app.core.sql import engine
from app.db.models import Dataset
from app.i18n.loader import Translator
from app.services import ml, sql

TEMPLATES = Path(__file__).resolve().parent.parent / "core" / "reports" / "templates"
_env = Environment(
    loader=FileSystemLoader(TEMPLATES),
    autoescape=select_autoescape(["html", "j2"]),
    trim_blocks=True,
    lstrip_blocks=True,
)

MONTHLY_SQL = """
SELECT strftime(d.month_start, '%Y-%m') AS month, SUM(f.amount_cad) AS spend, COUNT(*) AS contracts
FROM fact_contract f JOIN dim_date d USING (date_id)
WHERE f.amount_cad IS NOT NULL
GROUP BY 1 ORDER BY 1
"""
SUPPLIERS_SQL = """
WITH spend AS (
  SELECT s.supplier_name AS name, SUM(f.amount_cad) AS spend
  FROM fact_contract f JOIN dim_supplier s USING (supplier_id)
  WHERE f.amount_cad IS NOT NULL
  GROUP BY 1
)
SELECT name, spend, spend / SUM(spend) OVER () AS share FROM spend ORDER BY spend DESC LIMIT 5
"""
MONTHS_SHOWN = 24
PEAK_RATIO = 2.0  # a month at least twice the average is called out as a peak


def summary(ds: Dataset, t: Translator) -> dict[str, Any]:
    """Machine values + localized labels for the dataset's executive view."""
    star = sql.ensure_star(ds)
    kpis = {k["kpi_id"]: k for k in sql.kpis(ds, t)}
    monthly_rows = engine.run(star, MONTHLY_SQL).rows[-MONTHS_SHOWN:]
    monthly = [
        {"month": m, "spend": round(float(s or 0), 2), "contracts": int(c)}
        for m, s, c in monthly_rows
    ]
    peak = None
    if monthly:
        mean = sum(m["spend"] for m in monthly) / len(monthly)
        top = max(monthly, key=lambda m: m["spend"])
        ratio = top["spend"] / mean if mean else 0
        peak = {**top, "ratio": round(ratio, 2), "is_peak": ratio >= PEAK_RATIO}
    suppliers = [
        {"name": n, "spend": round(float(s), 2), "share": round(float(sh), 4)}
        for n, s, sh in engine.run(star, SUPPLIERS_SQL).rows
    ]
    profile = ds.profile_json or {}
    quality_after = (profile.get("quality_after") or {}).get("score")
    red = ml.load_result(ds, "red_flags")
    red_flags = None
    if red and red.get("model_type") == "red_flags":
        reasons = Counter(r for item in red.get("items", []) for r in item.get("reasons", []))
        red_flags = {
            "flagged": red.get("flagged", 0),
            "contracts": red.get("contracts", 0),
            "top_reasons": [
                {"id": r, "label": t(f"models.red_flags.reasons.{r}"), "count": n}
                for r, n in reasons.most_common(3)
            ],
        }
    forecast = None
    fc = ml.load_result(ds, "forecast")
    if fc and fc.get("model_type") == "forecast":
        forecast = {"status": fc["status"], "card": ml.localize(fc, t)["card"]}
    seed = SEEDS.get(ds.slug or "")
    return {
        "dataset": {
            "id": str(ds.id),
            "slug": ds.slug,
            "name": t(f"datasets.{ds.slug}.name") if seed else ds.name,
            "jurisdiction": sql.jurisdiction(ds),
            "data_lang": ds.data_lang.value if ds.data_lang else None,
            "license": seed.license if seed else None,
            "source_url": seed.source_url if seed else None,
        },
        "origin": sql.star_origin(ds),
        "currency": "CAD",
        "kpis": kpis,
        "quality": {"before": ds.quality_score, "after": quality_after},
        "monthly": monthly,
        "peak": peak,
        "top_suppliers": suppliers,
        "red_flags": red_flags,
        "forecast": forecast,
        "fx_source": _fx_source(),
    }


def _fx_source() -> str:
    from app.services.cleaning import context

    sources = context().fx.sources
    return "; ".join(f"{cur}: {src}" for cur, src in sorted(sources.items()) if cur != "CAD")


def _kpi_text(kpi: dict[str, Any] | None, lang: str) -> str:
    if not kpi or kpi.get("value") is None:
        return "—"
    value, unit = kpi["value"], kpi["unit"]
    if unit == "currency":
        return fmt.money(value, kpi.get("currency") or "CAD", lang, short=True)
    if unit == "ratio":
        return fmt.percent(value, lang)
    if unit == "index":
        return fmt.number(value, lang, 3)
    return fmt.number(value, lang, 0)


def _chart(monthly: list[dict[str, Any]], peak: dict[str, Any] | None, lang: str) -> dict[str, Any]:
    """Bar geometry for the inline SVG (the report has no JavaScript)."""
    width, height, pad = 640, 200, 24
    top = max((m["spend"] for m in monthly), default=0) or 1
    step = (width - 2 * pad) / max(len(monthly), 1)
    bars = []
    for i, m in enumerate(monthly):
        h = (height - 2 * pad) * m["spend"] / top
        bars.append(
            {
                "x": round(pad + i * step + step * 0.12, 1),
                "y": round(height - pad - h, 1),
                "w": round(step * 0.76, 1),
                "h": round(h, 1),
                "peak": bool(peak and peak["is_peak"] and m["month"] == peak["month"]),
                "title": f"{fmt.month(m['month'], lang)}: {fmt.money(m['spend'], 'CAD', lang)}",
                "label": fmt.month(m["month"], lang, short=True) if i % 6 == 0 else "",
            }
        )
    return {
        "width": width,
        "height": height,
        "pad": pad,
        "bars": bars,
        "top_label": fmt.money(top, "CAD", lang, short=True),
    }


def render_html(ds: Dataset, lang: str) -> str:
    t = Translator(lang)
    data = summary(ds, t)
    k = data["kpis"]
    today = datetime.now(UTC).date().isoformat()
    date_text = f"{int(today[8:10])} {fmt.month(today[:7], lang)}"
    texts: dict[str, Any] = {
        "summary": t(
            "reports.summary.text",
            contracts=_kpi_text(k.get("contract_count"), lang),
            total=_kpi_text(k.get("total_spend"), lang),
            direct=_kpi_text(k.get("direct_award_share"), lang),
            hhi=_kpi_text(k.get("hhi"), lang),
        ),
    }
    q = data["quality"]
    if data["origin"] == "clean" and q["after"] is not None:
        texts["quality"] = t("reports.summary.quality", before=q["before"], after=q["after"])
    else:
        texts["quality"] = t("reports.summary.quality_recommended", before=q["before"])
    monthly, peak = data["monthly"], data["peak"]
    if monthly:
        texts["chart"] = t(
            "reports.monthly.chart",
            first=fmt.month(monthly[0]["month"], lang),
            last=fmt.month(monthly[-1]["month"], lang),
        )
        texts["finding"] = (
            t(
                "reports.monthly.peak",
                month=fmt.month(peak["month"], lang),
                amount=fmt.money(peak["spend"], "CAD", lang, short=True),
                ratio=fmt.number(peak["ratio"], lang, 1),
            )
            if peak and peak["is_peak"]
            else t("reports.monthly.flat")
        )
    if data["red_flags"]:
        rf = data["red_flags"]
        texts["red_flags"] = t(
            "reports.red_flags.text",
            flagged=fmt.number(rf["flagged"], lang),
            contracts=fmt.number(rf["contracts"], lang),
            reasons=", ".join(
                f"{r['label']} ({fmt.number(r['count'], lang)})" for r in rf["top_reasons"]
            ),
        )
    seed = data["dataset"]
    texts["source"] = (
        t("reports.notes.source", publisher=seed["name"], license=seed["license"])
        if seed["license"]
        else t("reports.notes.upload", name=seed["name"])
    )
    kpi_ids = (
        "total_spend",
        "contract_count",
        "avg_value",
        "direct_award_share",
        "hhi",
        "quality_score",
    )
    tiles = [
        {"name": k[i]["name"], "value": _kpi_text(k[i], lang), "definition": k[i]["definition"]}
        for i in kpi_ids
        if i in k
    ]
    template = _env.get_template("report.html.j2")
    return template.render(
        lang=lang,
        t=t,
        data=data,
        texts=texts,
        tiles=tiles,
        date=date_text,
        chart=_chart(monthly, peak, lang) if monthly else None,
        suppliers=[
            {
                "name": s["name"],
                "spend": fmt.money(s["spend"], "CAD", lang),
                "share": fmt.percent(s["share"], lang),
            }
            for s in data["top_suppliers"]
        ],
    )
