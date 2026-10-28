"""RFC 7807 problem responses with a stable ``code`` and localized ``title``/``detail``."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

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
