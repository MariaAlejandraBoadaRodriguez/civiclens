"""Migration 001 applies on a fresh DB, matches the models, and downgrades cleanly.

Runs on SQLite always; also on PostgreSQL when TEST_DATABASE_URL is set (CI service).
"""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app.db.models import Base

API_DIR = Path(__file__).resolve().parent.parent
TABLES = {"api_keys", "datasets", "recipes", "jobs", "audit_log"}


def _urls(tmp_path: Path) -> list[str]:
    urls = [f"sqlite:///{tmp_path / 'migrations.db'}"]
    if pg := os.environ.get("TEST_DATABASE_URL"):
        urls.append(pg)
    return urls


def _config(url: str) -> Config:
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "app" / "db" / "migrations"))
    cfg.cmd_opts = type("Opts", (), {"x": [f"url={url}"]})()
    return cfg


@pytest.fixture(params=["sqlite", "postgresql"])
def db_url(request: pytest.FixtureRequest, tmp_path: Path) -> str:
    urls = {u.split(":")[0].split("+")[0]: u for u in _urls(tmp_path)}
    if request.param not in urls:
        pytest.skip("TEST_DATABASE_URL not set")
    url = urls[request.param]
    command.downgrade(_config(url), "base")  # start from an empty schema
    return url


def test_upgrade_creates_all_tables(db_url: str) -> None:
    command.upgrade(_config(db_url), "head")
    tables = set(inspect(create_engine(db_url)).get_table_names())
    assert TABLES <= tables
    assert "alembic_version" in tables


def test_models_match_migrations(db_url: str) -> None:
    command.upgrade(_config(db_url), "head")
    with create_engine(db_url).connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], f"Models and migrations differ: {diff}"


def test_downgrade_to_base(db_url: str) -> None:
    cfg = _config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    tables = set(inspect(create_engine(db_url)).get_table_names())
    assert not (TABLES & tables)
