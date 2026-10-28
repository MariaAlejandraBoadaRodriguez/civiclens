"""CivicLens API entry point."""

import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.problems import ProblemError, problem_handler, validation_handler
from app.api.v1 import datasets, jobs
from app.config import settings
from app.i18n.loader import Translator, negotiate


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if settings.warm_seeds:
        from app.services.datasets import warm_seeds

        threading.Thread(target=warm_seeds, name="warm-seeds", daemon=True).start()
    yield


app = FastAPI(
    title="CivicLens API",
    version="0.2.0",
    description="Public-sector data analytics engine: ingest, clean, model, predict and report.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    expose_headers=["Content-Language", "Location"],
)
app.add_exception_handler(ProblemError, problem_handler)
app.add_exception_handler(RequestValidationError, validation_handler)


@app.middleware("http")
async def locale_middleware(request: Request, call_next):
    """Negotiate the language once per request (ADR-0007) and echo it back."""
    request.state.t = Translator(negotiate(request.headers.get("accept-language")))
    response = await call_next(request)
    response.headers.setdefault("Content-Language", request.state.t.lang)
    return response


app.include_router(datasets.router)
app.include_router(jobs.router)


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    """Liveness probe used by the uptime monitor and deploy smoke tests."""
    return {"status": "ok", "service": "civiclens-api", "version": app.version}
