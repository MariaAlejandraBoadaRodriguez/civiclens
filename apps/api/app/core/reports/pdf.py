"""Executive report as PDF (A4), drawn with fpdf2 from the same context as the HTML report.

fpdf2 is pure Python and light (no browser, no Cairo/Pango as WeasyPrint needs), so the PDF is
rendered inside the API's 512 MB. The built-in Helvetica covers Latin-1: every Spanish and
French character. Anything outside it (rare in supplier names) is transliterated, never dropped.
"""

from __future__ import annotations

import unicodedata
from typing import Any

INK = (15, 27, 45)
TEXT = (31, 42, 55)
MUTED = (75, 85, 99)
LINE = (215, 221, 228)
PRIMARY = (29, 78, 216)
FLAG = (180, 83, 9)
FLAG_TINT = (253, 241, 228)
FLAG_TEXT = (124, 45, 18)

_REPLACE = {
    "—": "-",
    "–": "-",
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "…": "...",
    "•": "·",
    "→": "->",
    "≈": "~",
    " ": " ",
    " ": " ",
}


def latin1(text: Any) -> str:
    """Text the core fonts can draw: Latin-1 kept, the rest transliterated (é stays é)."""
    out = []
    for ch in str(text):
        ch = _REPLACE.get(ch, ch)
        try:
            ch.encode("latin-1")
            out.append(ch)
        except UnicodeEncodeError:
            base = unicodedata.normalize("NFKD", ch).encode("latin-1", "ignore").decode("latin-1")
            out.append(base or "?")
    return "".join(out)


def responsible_pdf(pdf: Any, notice: dict[str, Any], width: float) -> None:
    """The responsible-use box (flags are leads, verify the source, data as published)."""
    pdf.set_fill_color(*FLAG_TINT)
    pdf.set_text_color(*FLAG_TEXT)
    pdf.set_font("Helvetica", "B", 10)
    pdf.multi_cell(width, 6, latin1(notice["heading"]), fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=9)
    for item in notice["items"]:
        pdf.multi_cell(width, 5, latin1(f"-  {item}"), fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(
        width,
        5,
        latin1(f"{notice['guide']}: {notice['url']}"),
        fill=True,
        link=notice["url"],
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(2)


def render(ctx: dict[str, Any]) -> bytes:
    from fpdf import FPDF  # imported here: only report requests pay for it

    t = ctx["t"]
    data, texts = ctx["data"], ctx["texts"]

    class Report(FPDF):
        def footer(self) -> None:
            self.set_y(-14)
            self.set_font("Helvetica", size=8)
            self.set_text_color(*MUTED)
            self.cell(0, 6, latin1(t("reports.footer", date=ctx["date"])), align="L")
            self.cell(0, 6, f"{self.page_no()}/{{nb}}", align="R")

    pdf = Report(format="A4", unit="mm")
    pdf.set_title(latin1(f"{t('reports.title')} · {data['dataset']['name']}"))
    pdf.set_lang(ctx["lang"])
    pdf.set_author("CivicLens")
    pdf.set_creator("CivicLens")
    pdf.set_margins(18, 16, 18)
    pdf.set_auto_page_break(True, margin=18)
    pdf.alias_nb_pages()
    pdf.add_page()
    width = pdf.w - pdf.l_margin - pdf.r_margin

    def heading(text: str) -> None:
        if pdf.get_y() > pdf.h - 50:
            pdf.add_page()
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(*INK)
        pdf.cell(0, 8, latin1(text), new_x="LMARGIN", new_y="NEXT")

    def para(text: str, size: float = 10, color: tuple[int, int, int] = TEXT) -> None:
        pdf.set_font("Helvetica", size=size)
        pdf.set_text_color(*color)
        pdf.multi_cell(0, size * 0.5, latin1(text), align="L", new_x="LMARGIN", new_y="NEXT")

    # Title
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(*INK)
    pdf.cell(0, 11, latin1(t("reports.title")), new_x="LMARGIN", new_y="NEXT")
    para(t("reports.subtitle", dataset=data["dataset"]["name"], date=ctx["date"]), 10, MUTED)
    pdf.set_draw_color(*INK)
    pdf.set_line_width(0.8)
    pdf.line(pdf.l_margin, pdf.get_y() + 2, pdf.l_margin + width, pdf.get_y() + 2)
    pdf.ln(4)

    heading(t("reports.summary.heading"))
    para(texts["summary"])
    pdf.ln(1)
    para(texts["quality"])
    pdf.ln(2)
    responsible_pdf(pdf, ctx["responsible"], width)

    # KPI tiles, three per row
    heading(t("reports.kpis.heading"))
    gap, cols, tile_h = 4, 3, 24
    tile_w = (width - gap * (cols - 1)) / cols
    pdf.set_line_width(0.3)
    pdf.set_draw_color(*LINE)
    top = pdf.get_y()
    for i, tile in enumerate(ctx["tiles"]):
        col, row = i % cols, i // cols
        x, y = pdf.l_margin + col * (tile_w + gap), top + row * (tile_h + gap)
        pdf.rect(x, y, tile_w, tile_h, style="D", round_corners=True, corner_radius=2)
        pdf.set_xy(x + 3, y + 2.5)
        pdf.set_font("Helvetica", size=8.5)
        pdf.set_text_color(*MUTED)
        pdf.cell(tile_w - 6, 4, latin1(tile["name"]))
        pdf.set_xy(x + 3, y + 8)
        pdf.set_font("Helvetica", "B", 15)
        pdf.set_text_color(*INK)
        pdf.cell(tile_w - 6, 8, latin1(tile["value"]))
    rows = (len(ctx["tiles"]) + cols - 1) // cols
    pdf.set_xy(pdf.l_margin, top + rows * (tile_h + gap) - tile_h - gap)
    pdf.ln(tile_h + 2)
    para(t("reports.kpis.currency_note"), 8.5, MUTED)

    # Monthly spend chart
    heading(t("reports.monthly.heading"))
    chart = ctx["chart"]
    if chart:
        chart_h = 46
        if pdf.get_y() + chart_h + 20 > pdf.h - 18:
            pdf.add_page()
        x0, y0 = pdf.l_margin, pdf.get_y() + 2
        para_y = y0 + chart_h + 6
        bars = chart["bars"]
        step = width / max(len(bars), 1)
        top = max((b["h"] for b in bars), default=0) or 1
        pdf.set_font("Helvetica", size=7.5)
        pdf.set_text_color(*MUTED)
        pdf.set_xy(x0, y0 - 1)
        pdf.cell(0, 3, latin1(chart["top_label"]))
        for i, bar in enumerate(bars):
            h = (chart_h - 8) * bar["h"] / top
            pdf.set_fill_color(*(FLAG if bar["peak"] else PRIMARY))
            if h > 0:
                pdf.rect(x0 + i * step + step * 0.12, y0 + chart_h - h, step * 0.76, h, style="F")
            if bar["label"]:
                pdf.set_xy(x0 + i * step, y0 + chart_h + 0.5)
                pdf.cell(step * 4, 4, latin1(bar["label"]))
        pdf.set_draw_color(*LINE)
        pdf.line(x0, y0 + chart_h, x0 + width, y0 + chart_h)
        pdf.set_xy(pdf.l_margin, para_y)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*TEXT)
        pdf.multi_cell(0, 5, latin1(texts["finding"]), align="L", new_x="LMARGIN", new_y="NEXT")
        para(texts["chart"], 8.5, MUTED)
    else:
        para(t("reports.monthly.empty"))

    # Suppliers
    if ctx["suppliers"]:
        heading(t("reports.suppliers.heading"))
        widths = (width * 0.5, width * 0.25, width * 0.25)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*MUTED)
        for w, label, align in zip(
            widths,
            (
                t("reports.suppliers.supplier"),
                t("reports.suppliers.spend"),
                t("reports.suppliers.share"),
            ),
            ("L", "R", "R"),
            strict=True,
        ):
            pdf.cell(w, 7, latin1(label), border="B", align=align)
        pdf.ln()
        pdf.set_font("Helvetica", size=9.5)
        pdf.set_text_color(*TEXT)
        for s in ctx["suppliers"]:
            name = latin1(s["name"])
            while pdf.get_string_width(name) > widths[0] - 2 and len(name) > 4:
                name = name[:-2]
            if name != latin1(s["name"]):
                name = name.rstrip() + "..."
            pdf.cell(widths[0], 7, name, border="B")
            pdf.cell(widths[1], 7, latin1(s["spend"]), border="B", align="R")
            pdf.cell(widths[2], 7, latin1(s["share"]), border="B", align="R")
            pdf.ln()

    # Red flags with the human-review warning
    heading(t("reports.red_flags.heading"))
    para(texts.get("red_flags") or t("reports.red_flags.not_run"))
    pdf.ln(2)
    pdf.set_fill_color(*FLAG_TINT)
    pdf.set_text_color(*FLAG_TEXT)
    pdf.set_font("Helvetica", size=9.5)
    pdf.multi_cell(
        0,
        6,
        latin1(t("reports.red_flags.warning")),
        fill=True,
        align="L",
        new_x="LMARGIN",
        new_y="NEXT",
    )

    heading(t("reports.forecast.heading"))
    forecast = data.get("forecast")
    verdict = forecast and forecast["card"].get("verdict")
    para(verdict or t("reports.forecast.not_run"))

    heading(t("reports.notes.heading"))
    source = texts["source"]
    if data["dataset"].get("source_url"):
        source += f" {data['dataset']['source_url']}"
    for note in (
        source,
        t("reports.notes.fx", source=data["fx_source"]),
        t("reports.notes.values"),
    ):
        para(f"·  {note}", 9, MUTED)
    return bytes(pdf.output())
