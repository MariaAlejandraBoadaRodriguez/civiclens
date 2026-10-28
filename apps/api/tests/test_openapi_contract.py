"""openapi.yaml v0 ↔ docs/requirements.md traceability and i18n conventions."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
SPEC = yaml.safe_load((ROOT / "openapi.yaml").read_text(encoding="utf-8"))
REQUIREMENTS = (ROOT / "docs" / "requirements.md").read_text(encoding="utf-8")
STORIES = set(re.findall(r"^#### (US-\d{2})", REQUIREMENTS, flags=re.MULTILINE))
METHODS = {"get", "post", "put", "patch", "delete"}


def operations():
    for path, item in SPEC["paths"].items():
        for method, op in item.items():
            if method in METHODS:
                yield path, method, op


def test_every_endpoint_maps_to_existing_stories() -> None:
    for path, method, op in operations():
        refs = op.get("x-user-stories")
        assert refs, f"{method.upper()} {path} has no x-user-stories"
        unknown = set(refs) - STORIES
        assert not unknown, f"{method.upper()} {path} references unknown stories {unknown}"


def test_api_stories_are_covered() -> None:
    covered = {s for _, _, op in operations() for s in op["x-user-stories"]}
    for story in ("US-04", "US-05", "US-12", "US-16", "US-24", "US-25"):
        assert story in covered


def test_versioned_paths() -> None:
    for path, _, _ in operations():
        assert path == "/health" or path.startswith("/api/v1/"), path


def test_localized_operations_accept_language() -> None:
    """Operations that return localized text declare Accept-Language and Content-Language."""
    for path, method, op in operations():
        ok = next((r for code, r in op["responses"].items() if code.startswith("2")), {})
        if "Content-Language" in ok.get("headers", {}):
            params = [p.get("$ref", "") for p in op.get("parameters", [])]
            assert "#/components/parameters/AcceptLanguage" in params, f"{method} {path}"


def test_errors_are_rfc7807() -> None:
    for name, response in SPEC["components"]["responses"].items():
        assert "application/problem+json" in response["content"], name
