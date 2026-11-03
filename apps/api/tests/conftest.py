"""Test environment: throw-away SQLite DB and data directory, migrated with Alembic.

Environment variables are set before ``app`` is imported so settings pick them up.
"""

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="civiclens-tests-"))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP / 'app.db'}")
os.environ.setdefault("DATA_DIR", str(_TMP / "data"))
os.environ["WARM_SEEDS"] = "false"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

API_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session", autouse=True)
def _migrated_db() -> None:
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "app" / "db" / "migrations"))
    cfg.cmd_opts = type("Opts", (), {"x": [f"url={os.environ['DATABASE_URL']}"]})()
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def _fresh_rate_limits() -> None:
    """Every test starts with empty rate-limit windows. The test client is one "IP": without
    this, job-starting calls from earlier test files that fell in the same minute pushed a later
    test over the 12-per-minute heavy limit (an intermittent 429). The limits themselves are
    tested in test_public_api.py with explicit values."""
    from app.api.security import limiter

    limiter.reset()
