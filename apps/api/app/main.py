"""CivicLens API entry point."""

import logging
import os
import threading
import time
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
from app.api.v1 import dashboard, datasets, domain, jobs, keys, models, recipes, reports, sql
from app.config import settings
from app.core import jobs as job_runner
from app.core import observability as obs
from app.i18n.loader import Translator, negotiate

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if settings.json_logs:
        obs.configure_logging()
    job_runner.start(settings.job_runner)  # before any thread exists: the job runner forks
    if settings.warm_seeds:
        from app.services.datasets import warm_seeds

        threading.Thread(target=warm_seeds, name="warm-seeds", daemon=True).start()
    yield
    job_runner.stop()


app = FastAPI(
    title="CivicLens API",
    version="1.0.0",
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
    rid = obs.new_request_id(request.headers.get("x-request-id"))
    request.state.request_id = rid
    rid_token, locale_token = obs.request_id.set(rid), obs.request_locale.set(request.state.t.lang)
    started = time.perf_counter()
    try:
        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001 — logged; the client gets a stable code
            log.exception("unhandled error on %s %s", request.method, request.url.path)
            response = problem(request, 500, "server.internal")
        response.headers.setdefault("Content-Language", request.state.t.lang)
        response.headers["X-Request-ID"] = rid
        for name, value in obs.SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if settings.environment == "production":
            response.headers.setdefault("Strict-Transport-Security", obs.HSTS)
        obs.log_access(request.method, request.url.path, response.status_code, started)
        return response
    finally:
        obs.request_id.reset(rid_token)
        obs.request_locale.reset(locale_token)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=settings.allowed_origin_regex,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
    expose_headers=[
        "Content-Language",
        "Location",
        "Content-Disposition",
        "Retry-After",
        "X-Request-ID",
    ],
)


app.include_router(datasets.router)
app.include_router(domain.router)
app.include_router(jobs.router)
app.include_router(recipes.router)
app.include_router(sql.router)
app.include_router(models.router)
app.include_router(reports.router)
app.include_router(dashboard.router)
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


@app.get("/ready", tags=["ops"], responses={503: {"description": "Not ready"}})
def ready(request: Request):
    """Readiness: the database answers and DuckDB can run a query. Unlike ``/health`` (the
    process is up), a failure here means requests would fail."""
    from sqlalchemy import text

    from app.db.session import SessionLocal

    checks: dict[str, str] = {}
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:  # noqa: BLE001 — reported, not raised
        log.exception("readiness: database")
        checks["database"] = "error"
    try:
        import duckdb

        duckdb.connect(":memory:").execute("SELECT 1").fetchone()
        checks["duckdb"] = "ok"
    except Exception:  # noqa: BLE001
        log.exception("readiness: duckdb")
        checks["duckdb"] = "error"
    if all(v == "ok" for v in checks.values()):
        return {"status": "ready", "checks": checks}
    return problem(
        request,
        503,
        "server.not_ready",
        checks=", ".join(k for k, v in checks.items() if v != "ok"),
    )
