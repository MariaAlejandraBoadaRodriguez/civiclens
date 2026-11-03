"""Build the demo datasets ahead of time: ``python -m app.prebuild`` (Docker build step).

Building the three seeds needs ~700 MB of RAM for a minute or two; the free Render instance
has 512 MB. Doing it while the image is built keeps the running API small, and a cold start
only has to boot uvicorn. Needs the database migrated first (``alembic upgrade head``).
"""

from __future__ import annotations

import logging

from app.core.seed.registry import SEEDS
from app.db.session import SessionLocal
from app.services import sql
from app.services.datasets import ensure_seed


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    for seed in SEEDS.values():
        with SessionLocal() as session:
            ds = ensure_seed(session, seed)
            sql.ensure_star(ds)  # the SQL lab and the ML lab read it


if __name__ == "__main__":
    main()
