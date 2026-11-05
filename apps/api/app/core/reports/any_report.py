"""Executive report for any table (HTML + PDF), from the same overview the dashboard shows:
summary, KPI tiles, and each section's written finding with its bars. No scripts: the HTML is
served with a CSP that forbids them."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.core.reports import format as fmt
from app.core.reports.pdf import INK, LINE, MUTED, PRIMARY, TEXT, latin1


def tile_value(kpi: dict[str, Any], lang: str) -> str:
    value = kpi.get("value")
    if value is None:
        return "—"
    unit = kpi.get("unit")
    if unit == "ratio":
        return fmt.percent(value, lang)
    if unit == "amount" or abs(value) >= 100_000:
        return fmt.compact(value, lang)
    if unit in ("count", "score") or float(value).is_integer():
        return fmt.number(value, lang)
    return fmt.number(value, lang, 2)


def value_text(value: float | None, unit: str, lang: str) -> str:
    if value is None:
        return "—"
    if unit == "ratio":
        return fmt.percent(value, lang)
    if unit == "r":
        return fmt.number(value, lang, 2)
    if unit == "amount":
        return fmt.compact(value, lang)
    return fmt.number(value, lang)


def context(ds: Any, overview: dict[str, Any], t: Any, name: str, source: str) -> dict[str, Any]:
    lang = t.lang
    today = datetime.now(UTC).date().isoformat()
    sections = []
    for s in overview["sections"]:
        values = [abs(r["value"] or 0) for r in s["rows"]]
        top = max(values) or 1
        bars = [
            {
                "label": r["label"],
                "width": round(100 * abs(r["value"] or 0) / top, 1),
                "text": value_text(r["value"], s.get("unit", "count"), lang),
            }
            for r in s["rows"][:12]
        ]
        sections.append({"title": s["title"], "finding": s["finding"], "bars": bars})
    q = overview["quality"]
    quality = (
        t("reports.summary.quality", before=q["before"], after=q["after"])
        if q["after"] is not None
        else t("reports.summary.quality_recommended", before=q["before"])
    )
    return {
        "lang": lang,
        "t": t,
        "name": name,
        "date": f"{int(today[8:10])} {fmt.month(today[:7], lang)}",
        "domain": overview["domain"]["name"],
        "summary": t(
            "reports_any.summary",
            rows=fmt.number(overview["rows"], lang),
            columns=fmt.number(overview["columns"], lang),
            sections=len(sections),
        ),
        "quality": quality,
        "tiles": [
            {"name": k["name"], "value": tile_value(k, lang), "definition": k["definition"]}
            for k in overview["kpis"]
        ],
        "sections": sections,
        "source": source,
    }


def render_pdf(ctx: dict[str, Any]) -> bytes:
    from fpdf import FPDF

    t = ctx["t"]

    class Report(FPDF):
        def footer(self) -> None:
            self.set_y(-14)
            self.set_font("Helvetica", size=8)
            self.set_text_color(*MUTED)
            self.cell(0, 6, latin1(t("reports.footer", date=ctx["date"])), align="L")
            self.cell(0, 6, f"{self.page_no()}/{{nb}}", align="R")

    pdf = Report(format="A4", unit="mm")
    pdf.set_title(latin1(f"{t('reports_any.title')} · {ctx['name']}"))
    pdf.set_lang(ctx["lang"])
    pdf.set_author("CivicLens")
    pdf.set_margins(18, 16, 18)
    pdf.set_auto_page_break(True, margin=18)
    pdf.alias_nb_pages()
    pdf.add_page()
    width = pdf.w - pdf.l_margin - pdf.r_margin

    def text(value: str, size: float = 10, color=TEXT, style: str = "") -> None:
        pdf.set_font("Helvetica", style=style, size=size)
        pdf.set_text_color(*color)
        pdf.multi_cell(width, size * 0.5, latin1(value), new_x="LMARGIN", new_y="NEXT")

    text(t("reports_any.title"), 20, INK, "B")
    text(
        t("reports_any.subtitle", dataset=ctx["name"], date=ctx["date"], domain=ctx["domain"]),
        9,
        MUTED,
    )
    pdf.ln(3)
    text(ctx["summary"])
    text(ctx["quality"])
    pdf.ln(2)
    text(t("reports.kpis.heading"), 13, INK, "B")
    for tile in ctx["tiles"]:
        text(f"{tile['name']}: {tile['value']}", 10, INK, "B")
        text(tile["definition"], 8, MUTED)
    for s in ctx["sections"]:
        if pdf.get_y() > pdf.h - 60:
            pdf.add_page()
        pdf.ln(3)
        text(s["title"], 12, INK, "B")
        text(s["finding"], 10)
        pdf.ln(1)
        label_w, value_w = 55, 28
        track_w = width - label_w - value_w - 4
        for bar in s["bars"]:
            y = pdf.get_y()
            pdf.set_font("Helvetica", size=8)
            pdf.set_text_color(*TEXT)
            label = latin1(bar["label"])
            while pdf.get_string_width(label) > label_w - 2 and len(label) > 3:
                label = label[:-4] + "..."
            pdf.cell(label_w, 5, label)
            pdf.set_fill_color(*LINE)
            pdf.rect(pdf.l_margin + label_w, y + 1.5, track_w, 2.5, style="F")
            pdf.set_fill_color(*PRIMARY)
            pdf.rect(
                pdf.l_margin + label_w,
                y + 1.5,
                max(0.5, track_w * bar["width"] / 100),
                2.5,
                style="F",
            )
            pdf.set_x(pdf.l_margin + label_w + track_w + 4)
            pdf.cell(value_w, 5, latin1(bar["text"]), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    text(ctx["source"], 8, MUTED)
    text(t("reports_any.values"), 8, MUTED)
    return bytes(pdf.output())
