"""Request IDs, JSON logs, security headers and readiness (ROADMAP §5)."""

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.config import DEV_DATABASE_URL, settings
from app.core import observability as obs
from app.main import app

client = TestClient(app)


def test_every_answer_has_a_request_id_and_security_headers() -> None:
    for path in ("/health", "/api/v1/datasets", "/api/v1/nothing-here"):
        r = client.get(path)
        assert len(r.headers["x-request-id"]) == 32
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["x-frame-options"] == "DENY"
        assert r.headers["referrer-policy"] == "no-referrer"
        assert "strict-transport-security" not in r.headers  # only in production (HTTPS)
    mine = client.get("/health", headers={"X-Request-ID": "trace-123"})
    assert mine.headers["x-request-id"] == "trace-123"  # a caller's safe ID is kept
    forged = client.get("/health", headers={"X-Request-ID": 'x" injected'})
    assert forged.headers["x-request-id"] != 'x" injected'


def test_hsts_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "environment", "production")
    assert client.get("/health").headers["strict-transport-security"].startswith("max-age=")


def test_report_html_cannot_run_scripts() -> None:
    r = client.get("/api/v1/reports/contracts_qc?lang=es")
    assert r.status_code == 200
    assert r.headers["content-security-policy"].startswith("default-src 'none'")


def test_ready_checks_database_and_duckdb(monkeypatch: pytest.MonkeyPatch) -> None:
    ok = client.get("/ready")
    assert ok.status_code == 200 and ok.json() == {
        "status": "ready",
        "checks": {"database": "ok", "duckdb": "ok"},
    }
    from app.db import session as db_session

    class Broken:
        def __enter__(self):  # noqa: ANN204
            raise RuntimeError("database down")

        def __exit__(self, *_: object) -> None: ...

    monkeypatch.setattr(db_session, "SessionLocal", lambda: Broken())
    r = client.get("/ready", headers={"Accept-Language": "es"})
    assert r.status_code == 503 and r.json()["code"] == "server.not_ready"
    assert r.json()["title"] == "El servicio no está listo" and "database" in r.json()["detail"]


def test_json_log_lines_carry_request_id_and_locale_but_no_query_or_key() -> None:
    records: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(obs.JsonFormatter().format(record))

    handler = Capture()
    obs.access_log.addHandler(handler)
    obs.access_log.setLevel(logging.INFO)
    try:
        client.get(
            "/api/v1/datasets?source=seed",
            headers={
                "X-Request-ID": "req-42",
                "Accept-Language": "es",
                "X-API-Key": "cl_live_x.secret",
            },
        )
    finally:
        obs.access_log.removeHandler(handler)
    line = json.loads(records[-1])
    assert line["request_id"] == "req-42" and line["locale"] == "es"
    assert line["path"] == "/api/v1/datasets" and line["status"] == 401  # unknown key
    assert "source=seed" not in records[-1] and "secret" not in records[-1]


@pytest.mark.parametrize(
    ("env", "message"),
    [
        ({"database_url": DEV_DATABASE_URL}, "DATABASE_URL is the development default"),
        (
            {
                "database_url": "sqlite:////srv/var/x.db",
                "allowed_origins": ["http://localhost:3000"],
            },
            "https origins only",
        ),
        (
            {
                "database_url": "sqlite:////srv/var/x.db",
                "allowed_origins": ["https://a.example"],
                "admin_api_token": "short",
            },
            "ADMIN_API_TOKEN",
        ),
    ],
)
def test_production_fails_fast_on_unsafe_configuration(env: dict, message: str) -> None:
    from app.config import Settings

    with pytest.raises(ValueError, match=message):
        Settings(environment="production", **env)


def test_render_production_configuration_is_accepted() -> None:
    from app.config import Settings

    ok = Settings(
        environment="production",
        database_url="sqlite:////srv/var/civiclens.db",
        allowed_origins=["https://civiclens-eosin.vercel.app"],
        admin_api_token="x" * 48,
    )
    assert ok.environment == "production"
