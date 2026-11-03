"""Slice 5e: API keys (argon2, scoped, revocable), admin, rate limit, report, locale contract."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.security import limiter
from app.config import settings
from app.db.models import ApiKey, AuditLog
from app.db.session import SessionLocal
from app.main import app

client = TestClient(app)
ADMIN = {"Authorization": "Bearer test-admin-token", "X-Admin-Login": "owner"}
ORIGIN = "http://localhost:3000"


@pytest.fixture(autouse=True)
def _admin_and_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "admin_api_token", "test-admin-token")
    monkeypatch.setattr(settings, "allowed_origins", [ORIGIN])
    limiter.reset()
    yield
    limiter.reset()


def _create(scopes: list[str], name: str = "agency") -> dict[str, Any]:
    r = client.post("/api/v1/keys", json={"name": name, "scopes": scopes}, headers=ADMIN)
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------------------------ admin + keys


def test_key_is_shown_once_and_only_its_argon2_hash_is_stored() -> None:
    created = _create(["models:run"])
    assert created["key"].startswith(created["prefix"] + ".")
    listed = client.get("/api/v1/keys", headers=ADMIN).json()["items"]
    mine = next(k for k in listed if k["id"] == created["id"])
    assert "key" not in mine and "hash" not in mine and mine["scopes"] == ["models:run"]
    with SessionLocal() as session:
        row = session.get(ApiKey, __import__("uuid").UUID(created["id"]))
        assert row.hash.startswith("$argon2id$") and created["key"] not in row.hash
        audit = session.query(AuditLog).filter(AuditLog.target == f"api_key:{row.id}").all()
        assert [a.action for a in audit] == ["api_key.created"] and audit[0].actor == "owner"


@pytest.mark.parametrize(
    ("headers", "status", "code"),
    [
        ({}, 401, "auth.admin_required"),
        ({"Authorization": "Bearer wrong"}, 401, "auth.admin_required"),
    ],
)
def test_key_administration_needs_the_admin_token(headers: dict, status: int, code: str) -> None:
    r = client.get("/api/v1/keys", headers={**headers, "Accept-Language": "es"})
    assert r.status_code == status and r.json()["code"] == code
    assert r.json()["title"] == "Se requiere iniciar sesión como administrador"


def test_an_agency_key_cannot_manage_keys() -> None:
    key = _create(["reports:read"])["key"]
    r = client.get("/api/v1/keys", headers={"X-API-Key": key})
    assert r.status_code == 403 and r.json()["code"] == "auth.admin_only"


def test_admin_disabled_without_a_configured_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "admin_api_token", None)
    assert client.get("/api/v1/keys", headers=ADMIN).status_code == 401


# ------------------------------------------------------------------------------ keys on routes


def test_unknown_malformed_and_revoked_keys_are_401_everywhere() -> None:
    created = _create(["reports:read"])
    ok = client.get("/api/v1/datasets", headers={"X-API-Key": created["key"]})
    assert ok.status_code == 200
    assert client.delete(f"/api/v1/keys/{created['id']}", headers=ADMIN).status_code == 204
    for key in (created["key"], "nonsense", created["prefix"] + ".wrong-secret"):
        r = client.get("/api/v1/datasets", headers={"X-API-Key": key, "Accept-Language": "es"})
        assert r.status_code == 401 and r.json()["code"] == "auth.invalid_key"
        assert r.json()["title"] == "Clave de API no válida"
        assert r.headers["content-type"].startswith("application/problem+json")
    assert (
        client.delete(f"/api/v1/keys/{created['id']}", headers=ADMIN).status_code == 204
    )  # idempotent
    assert (
        client.delete(
            "/api/v1/keys/00000000-0000-0000-0000-000000000000", headers=ADMIN
        ).status_code
        == 404
    )


def test_writes_need_a_key_with_the_right_scope_when_anonymous_writes_are_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "anonymous_writes", False)
    body = {"dataset_id": "contracts_ca"}
    anon = client.post("/api/v1/models/forecast/run", json=body)
    assert anon.status_code == 401 and anon.json()["code"] == "auth.missing_key"
    wrong = _create(["reports:read"])["key"]
    r = client.post("/api/v1/models/forecast/run", json=body, headers={"X-API-Key": wrong})
    assert r.status_code == 403 and r.json()["params"] == {"scope": "models:run"}
    right = _create(["models:run"])
    r = client.post("/api/v1/models/forecast/run", json=body, headers={"X-API-Key": right["key"]})
    assert r.status_code == 202, r.text
    from app.db.models import Job

    with SessionLocal() as session:
        job = session.get(Job, __import__("uuid").UUID(r.json()["id"]))
        assert str(job.api_key_id) == right["id"]  # the job remembers which key started it
        key = session.get(ApiKey, job.api_key_id)
        assert key.last_used_at is not None


def test_the_public_demo_still_writes_anonymously() -> None:
    assert settings.anonymous_writes is True
    r = client.post("/api/v1/recipes", json={"name": "demo", "steps": []})
    assert r.status_code == 201


# ----------------------------------------------------------------- rate limit, CORS, 500


def test_rate_limit_answers_429_with_retry_after_cors_and_translation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "rate_limit_anonymous", 3)
    headers = {"Origin": ORIGIN, "Accept-Language": "es"}
    for _ in range(3):
        assert client.get("/api/v1/guided-queries", headers=headers).status_code == 200
    r = client.get("/api/v1/guided-queries", headers=headers)
    assert r.status_code == 429 and r.json()["code"] == "rate_limit.exceeded"
    assert 1 <= int(r.headers["retry-after"]) <= 60
    assert r.json()["title"] == "Demasiadas solicitudes"
    assert r.headers["access-control-allow-origin"] == ORIGIN  # readable by the browser
    assert client.get("/health").status_code == 200  # ops endpoints are not limited


def test_heavy_routes_have_their_own_stricter_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "rate_limit_heavy_anonymous", 1)
    body = {"dataset_id": "contracts_ca"}
    assert client.post("/api/v1/models/forecast/run", json=body).status_code == 202
    assert client.post("/api/v1/models/forecast/run", json=body).status_code == 429
    assert client.get("/api/v1/guided-queries").status_code == 200  # reads still fine


def test_a_key_has_its_own_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "rate_limit_anonymous", 1)
    key = _create(["reports:read"])["key"]
    client.get("/api/v1/guided-queries")
    assert client.get("/api/v1/guided-queries").status_code == 429
    assert client.get("/api/v1/guided-queries", headers={"X-API-Key": key}).status_code == 200


def test_errors_carry_cors_headers_even_when_unexpected(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import sql

    def boom(*_: Any, **__: Any) -> None:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(sql, "kpis", boom)
    local = TestClient(app, raise_server_exceptions=False)
    r = local.get("/api/v1/kpis/secop_co", headers={"Origin": ORIGIN, "Accept-Language": "es"})
    assert r.status_code == 500 and r.json()["code"] == "server.internal"
    assert r.headers["access-control-allow-origin"] == ORIGIN
    bad_key = local.get("/api/v1/datasets", headers={"Origin": ORIGIN, "X-API-Key": "x"})
    assert bad_key.status_code == 401 and bad_key.headers["access-control-allow-origin"] == ORIGIN


# ------------------------------------------------------------------------------ report


def test_report_in_the_requested_language() -> None:
    en = client.get("/api/v1/reports/contracts_qc?lang=en")
    es = client.get("/api/v1/reports/contracts_qc", headers={"Accept-Language": "es"})
    assert en.status_code == es.status_code == 200
    assert en.headers["content-type"].startswith("text/html")
    assert en.headers["content-language"] == "en" and es.headers["content-language"] == "es"
    assert '<html lang="en">' in en.text and "Executive report" in en.text
    assert '<html lang="es">' in es.text and "Reporte ejecutivo" in es.text
    assert "Executive report" not in es.text
    # lang wins over Accept-Language
    forced = client.get("/api/v1/reports/contracts_qc?lang=en", headers={"Accept-Language": "es"})
    assert "Executive report" in forced.text and forced.headers["content-language"] == "en"
    # Data values are never translated: the same supplier names appear in both reports.
    import re

    names = lambda html: re.findall(r"<tr><td>(.*?)</td>", html)  # noqa: E731
    assert names(en.text) and names(en.text) == names(es.text)
    assert "attachment" not in en.headers["content-disposition"]


def test_report_pdf_in_the_requested_language_and_unknown_dataset_is_404() -> None:
    import io

    from pypdf import PdfReader

    for lang, title in (("en", "Executive report"), ("es", "Reporte ejecutivo")):
        r = client.get(f"/api/v1/reports/contracts_qc?format=pdf&lang={lang}")
        assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
        assert r.headers["content-language"] == lang
        assert f"civiclens-report-contracts_qc-{lang}.pdf" in r.headers["content-disposition"]
        text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
        assert title in text
    es = "".join(
        p.extract_text()
        for p in PdfReader(
            io.BytesIO(client.get("/api/v1/reports/contracts_qc?format=pdf&lang=es").content)
        ).pages
    )
    assert "revisión humana" in es  # accents survive the core fonts
    assert client.get("/api/v1/reports/nope?format=pdf").status_code == 404


def test_report_needs_reports_read_when_called_with_a_key() -> None:
    no = _create(["models:run"])["key"]
    yes = _create(["reports:read"])["key"]
    assert client.get("/api/v1/reports/contracts_ca", headers={"X-API-Key": no}).status_code == 403
    assert client.get("/api/v1/reports/contracts_ca", headers={"X-API-Key": yes}).status_code == 200


# ------------------------------------------------------------------------------ locale contract

LOCALIZED = {
    "title",
    "detail",
    "name",
    "definition",
    "question",
    "explanation",
    "label",
    "what",
    "why",
    "learn_more",
    "hint",
    "card",
    "reason_labels",
    "category_label",
    "kpi_label",
    "op_labels",
    "candidate_labels",
    "pii_label",
    "data_lang_label",
    "description",
    "fx_note",
    "verdict",
    "labels",
    "label_en",
    "label_es",
}


def _machine(value: Any) -> Any:
    """The response without its human-readable (localized) fields."""
    if isinstance(value, dict):
        return {k: _machine(v) for k, v in value.items() if k not in LOCALIZED}
    if isinstance(value, list):
        return [_machine(v) for v in value]
    return value


@pytest.mark.parametrize(
    ("path", "has_text"),
    [
        ("/api/v1/datasets", True),
        ("/api/v1/datasets/contracts_qc", True),
        ("/api/v1/datasets/contracts_qc/profile", True),
        ("/api/v1/datasets/contracts_qc/issues", True),
        ("/api/v1/datasets/contracts_qc/schema", False),  # machine data only
        ("/api/v1/guided-queries", True),
        ("/api/v1/kpis/contracts_qc", True),
        ("/api/v1/datasets/nope", True),
        ("/api/v1/jobs/not-a-job", True),
    ],
)
def test_same_request_in_en_and_es_has_identical_machine_fields(path: str, has_text: bool) -> None:
    en = client.get(path, headers={"Accept-Language": "en"})
    es = client.get(path, headers={"Accept-Language": "es"})
    assert en.status_code == es.status_code
    assert en.headers["content-language"] == "en" and es.headers["content-language"] == "es"
    assert _machine(en.json()) == _machine(es.json())
    assert (en.json() != es.json()) == has_text  # only the human text changes


# ------------------------------------------------------------------------------ contract edges


def test_content_disposition_is_latin1_safe_for_any_name() -> None:
    from app.api.headers import content_disposition

    assert content_disposition("inline", "report-en.html") == 'inline; filename="report-en.html"'
    value = content_disposition("attachment", "Nettoyage_été_\U00106e9a_v1.py")
    value.encode("latin-1")  # Starlette encodes headers as latin-1
    assert 'filename="Nettoyage_t_v1.py"' in value
    assert "filename*=UTF-8''Nettoyage_%C3%A9t%C3%A9_%F4%86%BA%9A_v1.py" in value
    r = client.post("/api/v1/recipes", json={"name": "Limpieza — año 2024 ✓", "steps": []})
    export = client.get(f"/api/v1/recipes/{r.json()['id']}/export")
    assert (
        export.status_code == 200 and "filename*=UTF-8''" in export.headers["content-disposition"]
    )


def test_framework_errors_are_localized_problems_with_allow() -> None:
    r = client.get("/api/v1/nothing-here", headers={"Accept-Language": "es"})
    assert r.status_code == 404 and r.json()["code"] == "request.not_found"
    assert r.headers["content-type"].startswith("application/problem+json")
    r = client.put("/api/v1/keys", headers={"Accept-Language": "es"})
    assert r.status_code == 405 and r.json()["code"] == "request.method_not_allowed"
    assert set(r.headers["allow"].replace(" ", "").split(",")) >= {"GET", "POST"}
    stub = client.get("/api/v1/recipes/preview")
    assert stub.status_code == 405 and stub.headers["allow"] == "POST"


@pytest.mark.parametrize(
    ("path", "body"),
    [
        (
            "/api/v1/models/red_flags/reviews",
            {"dataset_id": "x", "contract_id": "c", "reviewed": "no"},
        ),
        ("/api/v1/models/forecast/run", {"dataset_id": "contracts_ca", "params": {"entity_id": 7}}),
    ],
)
def test_no_silent_type_coercion(path: str, body: dict) -> None:
    assert client.post(path, json=body).status_code == 422


def test_datasets_filter_accepts_every_documented_source() -> None:
    for source in ("seed", "upload", "api"):
        assert client.get(f"/api/v1/datasets?source={source}").status_code == 200
    assert client.get("/api/v1/datasets?source=other").status_code == 422


def test_allow_never_advertises_a_refusing_stub() -> None:
    r = client.options("/api/v1/recipes/preview")
    assert r.status_code == 405 and r.headers["allow"] == "POST"
    doc = client.post("/api/v1/recipes", json={"name": "doc", "steps": []}).json()
    exported = client.get(f"/api/v1/recipes/{doc['id']}/export?format=json").json()
    assert set(exported) == {"schema", "name", "version", "steps"}  # RecipeDocument


def test_client_ip_behind_a_proxy_cannot_be_forged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "rate_limit_anonymous", 1)
    monkeypatch.setattr(settings, "trusted_proxy_hops", 1)
    # Render appends the real client last; a caller-supplied left part changes nothing.
    first = {"X-Forwarded-For": "1.1.1.1, 203.0.113.7"}
    forged = {"X-Forwarded-For": "9.9.9.9, 203.0.113.7"}
    other = {"X-Forwarded-For": "198.51.100.2"}
    assert client.get("/api/v1/guided-queries", headers=first).status_code == 200
    assert client.get("/api/v1/guided-queries", headers=forged).status_code == 429
    assert client.get("/api/v1/guided-queries", headers=other).status_code == 200
