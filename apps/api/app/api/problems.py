"""RFC 7807 problem responses with a stable ``code`` and localized ``title``/``detail``."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.i18n.loader import Translator

PROBLEM_BASE = "https://civiclens.dev/problems/"


class ProblemError(Exception):
    def __init__(self, status: int, code: str, **params: Any) -> None:
        super().__init__(code)
        self.status, self.code, self.params = status, code, params


def problem_body(
    t: Translator, status: int, code: str, params: dict[str, Any], instance: str
) -> dict:
    return {
        "type": PROBLEM_BASE + code,
        "title": t(f"errors.{code}.title", **params),
        "status": status,
        "detail": t(f"errors.{code}.detail", **params),
        "instance": instance,
        "code": code,
        "params": params,
    }


def _respond(request: Request, status: int, code: str, params: dict[str, Any]) -> JSONResponse:
    t: Translator = getattr(request.state, "t", Translator("en"))
    return JSONResponse(
        problem_body(t, status, code, params, request.url.path),
        status_code=status,
        media_type="application/problem+json",
        headers={"Content-Language": t.lang},
    )


async def problem_handler(request: Request, exc: ProblemError) -> JSONResponse:
    return _respond(request, exc.status, exc.code, exc.params)


async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    fields = [".".join(str(p) for p in e.get("loc", ())) for e in exc.errors()]
    return _respond(request, 422, "request.invalid", {"fields": fields})


def iso_utc(value: datetime | None) -> str | None:
    """RFC 3339 timestamp with an explicit offset. SQLite returns naive datetimes (stored as
    UTC); without an offset they are not valid OpenAPI ``date-time`` values."""
    if value is None:
        return None
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).isoformat()


# Paths whose only methods are fixed, though a broader route (e.g. ``/recipes/{id}``) would
# also match them. Their stub routes raise 405 and must never appear in ``Allow``.
ONLY_METHODS: dict[str, list[str]] = {}


def only_methods(path: str, methods: list[str]) -> None:
    ONLY_METHODS[path] = methods


def _allowed_methods(request: Request) -> list[str]:
    """Every method some route serves for this path (Starlette lists only the first match).

    Asks the router itself, method by method, so nested/included routers are covered too.
    """
    from starlette.routing import Match

    if request.url.path in ONLY_METHODS:
        return ONLY_METHODS[request.url.path]
    allowed = []
    for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        scope = {**request.scope, "method": method, "type": "http"}
        if any(route.matches(scope)[0] == Match.FULL for route in request.app.routes):
            allowed.append(method)
    return allowed


async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Framework errors (unknown route, wrong method, unparsable body) as RFC 7807 problems."""
    if exc.status_code == 405:
        response = _respond(request, 405, "request.method_not_allowed", {"method": request.method})
        response.headers["Allow"] = ", ".join(_allowed_methods(request))
        return response
    if exc.status_code == 404:
        return _respond(request, 404, "request.not_found", {})
    if exc.status_code == 400:
        return _respond(request, 400, "request.malformed", {})
    return _respond(request, exc.status_code, "server.internal", {})
