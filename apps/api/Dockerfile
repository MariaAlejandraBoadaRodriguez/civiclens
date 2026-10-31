# Build from the repository root (the image needs data/seed):
#   docker build -f apps/api/Dockerfile .
FROM python:3.11-slim

# MALLOC_ARENA_MAX / ARROW_DEFAULT_MEMORY_POOL keep the API inside 512 MB (Render free):
# fewer glibc heap arenas across worker threads, and Arrow frees memory instead of pooling it.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SEED_DIR=/srv/data/seed \
    FX_PATH=/srv/data/fx_rates.csv \
    DATA_DIR=/srv/var \
    DATABASE_URL=sqlite:////srv/var/civiclens.db \
    MALLOC_ARENA_MAX=2 \
    ARROW_DEFAULT_MEMORY_POOL=system

WORKDIR /srv

COPY apps/api/pyproject.toml ./
COPY apps/api/alembic.ini ./
COPY apps/api/app ./app
RUN pip install --upgrade pip && pip install .
COPY data/seed/*.parquet ./data/seed/
COPY data/fx_rates.csv ./data/

# Demo datasets are built now, not at runtime: the free instance has 512 MB of RAM and
# building them takes ~700 MB. With another DATABASE_URL (docker compose → Postgres) the
# seeds are simply rebuilt at startup.
RUN mkdir -p /srv/var && alembic upgrade head && python -m app.prebuild
RUN useradd --create-home appuser && chown -R appuser /srv/var
USER appuser

EXPOSE 8000
# Migrations run before the API accepts traffic (ADR-0003).
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
