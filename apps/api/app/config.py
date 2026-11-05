"""Runtime configuration read from environment variables."""

from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_DATABASE_URL = "postgresql+psycopg://civiclens:civiclens@localhost:5432/civiclens"

# Repository checkout: apps/api/app/config.py → repo root. In the Docker image the file is
# /srv/app/config.py and data lives in /srv/data, so the root is /srv.
_HERE = Path(__file__).resolve()
REPO_ROOT = _HERE.parents[3] if len(_HERE.parents) > 3 else _HERE.parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "local"
    # One JSON object per log line, with request ID and locale (off in tests: pytest's capture).
    json_logs: bool = True
    allowed_origins: list[str] = ["http://localhost:3000"]
    # Extra origins by pattern, e.g. Vercel preview deployments of the web app.
    allowed_origin_regex: str | None = None
    default_locale: str = "en"
    database_url: str = DEV_DATABASE_URL

    # Files: committed seed Parquet (read-only) and a writable working directory.
    seed_dir: Path = REPO_ROOT / "data" / "seed"
    fx_path: Path = REPO_ROOT / "data" / "fx_rates.csv"
    data_dir: Path = REPO_ROOT / "data" / "runtime"
    upload_max_mb: int = 50
    upload_ttl_hours: int = 24
    # Build the three demo datasets in the background at startup (off in tests).
    warm_seeds: bool = True
    # Background jobs: "inline" (tests, local) or "fork" (Docker: each job in its own process,
    # see app/core/jobs.py).
    job_runner: str = "inline"

    # Public API (ROADMAP 5e). The public demo lets anonymous visitors write (upload, clean,
    # run models); an agency deployment sets ANONYMOUS_WRITES=false so writes need a key.
    anonymous_writes: bool = True
    # Shared with the web app's server, which calls /api/v1/keys after GitHub OAuth of the
    # allowlisted admin. Unset = key administration disabled.
    admin_api_token: str | None = None
    # Requests per minute: per IP for anonymous callers, per key for agencies; "heavy" = routes
    # that start background work (upload, apply recipe, run model).
    # Per caller IP (TRUSTED_PROXY_HOPS=1 behind Render's proxy), sized for a shared network: a
    # workshop or office of 10 visitors behind one IP makes ~530 requests and up to ~10 heavy
    # calls a minute (docs/capacity.md, k6 load/k6-visitors.js). Heavy jobs run one at a time,
    # so a higher heavy ceiling queues work; it does not add memory.
    rate_limit_anonymous: int = 1200
    rate_limit_key: int = 1200
    rate_limit_heavy_anonymous: int = 30
    rate_limit_heavy_key: int = 60
    # Proxies in front of the API that append to X-Forwarded-For (Render: 1). The client is the
    # entry that many hops from the right; entries further left are caller-controlled.
    trusted_proxy_hops: int = 0

    @model_validator(mode="after")
    def _production_is_configured(self) -> "Settings":
        """Fail fast at startup (ROADMAP §5): a production API with development defaults would
        start and then fail on the first request, or accept every origin."""
        if self.environment != "production":
            return self
        problems = []
        if self.database_url == DEV_DATABASE_URL:
            problems.append("DATABASE_URL is the development default")
        insecure = [o for o in self.allowed_origins if not o.startswith("https://")]
        if not self.allowed_origins or insecure:
            problems.append(
                f"ALLOWED_ORIGINS must list https origins only (got {insecure or 'none'})"
            )
        if self.admin_api_token is not None and len(self.admin_api_token) < 32:
            problems.append("ADMIN_API_TOKEN is shorter than 32 characters")
        if problems:
            raise ValueError("refusing to start in production: " + "; ".join(problems))
        return self


settings = Settings()
