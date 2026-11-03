"""CivicLens API entry point."""

import logging
import os
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.problems import (
    ProblemError,
    http_error_handler,
    problem_handler,
    validation_handler,
)
from app.api.security import problem, security_middleware
from app.api.v1 import datasets, jobs, keys, models, recipes, reports, sql
from app.config import settings
from app.core import jobs as job_runner
from app.i18n.loader import Translator, negotiate

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    job_runner.start(settings.job_runner)  # before any thread exists: the job runner forks
    if settings.warm_seeds:
        from app.services.datasets import warm_seeds

        threading.Thread(target=warm_seeds, name="warm-seeds", daemon=True).start()
    yield
    job_runner.stop()


app = FastAPI(
    title="CivicLens API",
    version="0.2.0",
    description="Public-sector data analytics engine: ingest, clean, model, predict and report.",
    lifespan=lifespan,
)

app.add_exception_handler(ProblemError, problem_handler)
app.add_exception_handler(RequestValidationError, validation_handler)
app.add_exception_handler(StarletteHTTPException, http_error_handler)

# Middleware order (Starlette: the last added is the outermost):
#   CORS → locale + error guard → security (key, rate limit) → routes.
# CORS is outermost so that every answer, a 401/429/500 included, carries CORS headers.
app.middleware("http")(security_middleware)


@app.middleware("http")
async def locale_middleware(request: Request, call_next):
    """Negotiate the language once per request (ADR-0007) and echo it back. An unexpected
    error becomes a localized 500 problem here, inside CORS (never a bare 500)."""
    request.state.t = Translator(negotiate(request.headers.get("accept-language")))
    try:
        response = await call_next(request)
    except Exception:  # noqa: BLE001 — logged; the client gets a stable code
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        response = problem(request, 500, "server.internal")
    response.headers.setdefault("Content-Language", request.state.t.lang)
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=settings.allowed_origin_regex,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
    expose_headers=["Content-Language", "Location", "Content-Disposition", "Retry-After"],
)


app.include_router(datasets.router)
app.include_router(jobs.router)
app.include_router(recipes.router)
app.include_router(sql.router)
app.include_router(models.router)
app.include_router(reports.router)
app.include_router(keys.router)


@app.get("/health", tags=["ops"])
def health() -> dict[str, str | None]:
    """Liveness probe used by the uptime monitor and deploy smoke tests. ``commit`` is the Git
    commit Render deployed, so the post-deploy smoke test knows the new version is live."""
    return {
        "status": "ok",
        "service": "civiclens-api",
        "version": app.version,
        "commit": os.environ.get("RENDER_GIT_COMMIT"),
    }
