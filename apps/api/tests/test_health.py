from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "civiclens-api"


def test_openapi_is_published() -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "CivicLens API"


def test_render_blueprint_matches_the_app() -> None:
    """render.yaml deploys this API: Dockerfile and health path exist; CORS covers Vercel."""
    import re
    from pathlib import Path

    import yaml

    root = Path(__file__).resolve().parents[3]
    service = yaml.safe_load((root / "render.yaml").read_text(encoding="utf-8"))["services"][0]
    assert (root / service["dockerfilePath"]).is_file()
    assert service["healthCheckPath"] == "/health"
    assert service["plan"] == "free"
    env = {v["key"]: v["value"] for v in service["envVars"]}
    assert "https://civiclens-eosin.vercel.app" in env["ALLOWED_ORIGINS"]
    pattern = re.compile(env["ALLOWED_ORIGIN_REGEX"])
    for origin in (
        "https://civiclens-eosin.vercel.app",
        "https://civiclens-git-fix-deploy-backend-maria-alejandra-boada-rodriguezs-projects.vercel.app",
        "https://civiclens-a1b2c3d4e-maria-alejandra-boada-rodriguezs-projects.vercel.app",
    ):
        assert pattern.fullmatch(origin), origin
    for origin in ("https://evil.vercel.app", "https://civiclens.vercel.app.evil.com"):
        assert not pattern.fullmatch(origin), origin
