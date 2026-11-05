"""Pre-launch for public feedback: the feedback issue form, the responsible-use guide and its
notice in every report (HTML + PDF, EN/ES), and the keep-warm schedule."""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[3]
client = TestClient(app)
GUIDE = {
    "en": "docs/responsible-use.md",
    "es": "docs/responsible-use.es.md",
}
HEADING = {"en": "Use this report responsibly", "es": "Usa este reporte con responsabilidad"}


def test_feedback_form_is_bilingual_and_asks_the_four_questions() -> None:
    form = yaml.safe_load((ROOT / ".github/ISSUE_TEMPLATE/feedback.yml").read_text("utf-8"))
    fields = {f["id"]: f for f in form["body"] if "id" in f}
    assert {"who", "tried", "confusing", "need", "page", "language"} <= set(fields)
    for f in fields.values():
        label = f["attributes"]["label"]
        assert " · " in label, label  # "English · Español"
    assert fields["who"]["validations"]["required"] and fields["tried"]["validations"]["required"]
    intro = next(f for f in form["body"] if f["type"] == "markdown")["attributes"]["value"]
    assert "personal data" in intro and "datos personales" in intro  # public issue: warn


def test_responsible_use_guide_exists_in_both_languages() -> None:
    en = (ROOT / GUIDE["en"]).read_text("utf-8")
    es = (ROOT / GUIDE["es"]).read_text("utf-8")
    assert "not accusations" in en and "original source" in en and "exactly as published" in en
    assert "no acusaciones" in es and "fuente original" in es and "tal como fueron publicados" in es
    assert "responsible-use.es.md" in en and "responsible-use.md" in es  # linked to each other


def _pdf_text(body: bytes) -> str:
    from pypdf import PdfReader

    return " ".join(page.extract_text() for page in PdfReader(io.BytesIO(body)).pages)


@pytest.fixture(scope="module")
def any_dataset() -> str:
    body = (ROOT / "data/fixtures/german_credit.csv").read_bytes()
    r = client.post("/api/v1/datasets", files={"file": ("german_credit.csv", body, "text/csv")})
    assert client.get(r.headers["location"]).json()["status"] == "succeeded"
    return r.json()["dataset"]["id"]


@pytest.mark.parametrize("lang", ["en", "es"])
@pytest.mark.parametrize("kind", ["procurement", "any"])
def test_every_report_carries_the_responsible_use_notice(
    lang: str, kind: str, any_dataset: str
) -> None:
    ref = "contracts_qc" if kind == "procurement" else any_dataset
    html = client.get(f"/api/v1/reports/{ref}?lang={lang}").text
    assert HEADING[lang] in html and GUIDE[lang] in html
    pdf = _pdf_text(client.get(f"/api/v1/reports/{ref}?lang={lang}&format=pdf").content)
    squashed = re.sub(r"\s+", " ", pdf)
    assert HEADING[lang] in squashed
    assert ("not accusations" if lang == "en" else "no acusaciones") in squashed


def _minutes(field: str, top: int) -> set[int]:
    if field == "*":
        return set(range(top))
    if field.startswith("*/"):
        return set(range(0, top, int(field[2:])))
    if "-" in field:
        a, b = field.split("-")
        return set(range(int(a), int(b) + 1))
    return {int(field)}


def test_keep_warm_pings_every_ten_minutes_from_7_to_23_bogota() -> None:
    wf = yaml.safe_load((ROOT / ".github/workflows/keep-warm.yml").read_text("utf-8"))
    on = wf.get("on", wf.get(True))  # PyYAML reads the key `on` as True
    fired: set[int] = set()  # minutes of the day, UTC
    for entry in on["schedule"]:
        minute, hour, *_ = entry["cron"].split()
        fired |= {h * 60 + m for h in _minutes(hour, 24) for m in _minutes(minute, 60)}
    bogota = {((m - 5 * 60) % 1440) for m in fired}  # UTC−5, no daylight saving
    expected = set(range(7 * 60, 23 * 60 + 1, 10))  # 07:00, 07:10 … 23:00
    assert bogota == expected
    step = wf["jobs"]["ping"]["steps"][0]["run"]
    assert "/health" in step


def test_rate_limits_fit_ten_visitors_behind_one_ip() -> None:
    """docs/capacity.md: 10 visitors on one shared IP (a workshop, an office, mobile CGNAT)
    make ~530 requests and up to ~10 heavy calls a minute; the old 300/12 answered 810 × 429."""
    from app.config import Settings

    defaults = Settings()
    assert defaults.rate_limit_anonymous >= 2 * 530
    assert defaults.rate_limit_heavy_anonymous >= 2 * 10
