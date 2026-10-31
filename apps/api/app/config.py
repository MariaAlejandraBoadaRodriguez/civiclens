"""Runtime configuration read from environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository checkout: apps/api/app/config.py → repo root. In the Docker image the file is
# /srv/app/config.py and data lives in /srv/data, so the root is /srv.
_HERE = Path(__file__).resolve()
REPO_ROOT = _HERE.parents[3] if len(_HERE.parents) > 3 else _HERE.parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "local"
    allowed_origins: list[str] = ["http://localhost:3000"]
    # Extra origins by pattern, e.g. Vercel preview deployments of the web app.
    allowed_origin_regex: str | None = None
    default_locale: str = "en"
    database_url: str = "postgresql+psycopg://civiclens:civiclens@localhost:5432/civiclens"

    # Files: committed seed Parquet (read-only) and a writable working directory.
    seed_dir: Path = REPO_ROOT / "data" / "seed"
    fx_path: Path = REPO_ROOT / "data" / "fx_rates.csv"
    data_dir: Path = REPO_ROOT / "data" / "runtime"
    upload_max_mb: int = 50
    upload_ttl_hours: int = 24
    # Build the three demo datasets in the background at startup (off in tests).
    warm_seeds: bool = True


settings = Settings()
