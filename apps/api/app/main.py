"""CivicLens API entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

app = FastAPI(
    title="CivicLens API",
    version="0.1.0",
    description="Public-sector data analytics engine: ingest, clean, model, predict and report.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    """Liveness probe used by the uptime monitor and deploy smoke tests."""
    return {"status": "ok", "service": "civiclens-api", "version": app.version}
