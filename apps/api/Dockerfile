# Build from the repository root (the image needs data/seed):
#   docker build -f apps/api/Dockerfile .
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SEED_DIR=/srv/data/seed \
    FX_PATH=/srv/data/fx_rates.csv \
    DATA_DIR=/srv/var

WORKDIR /srv

COPY apps/api/pyproject.toml ./
COPY apps/api/alembic.ini ./
COPY apps/api/app ./app
RUN pip install --upgrade pip && pip install .
COPY data/seed/*.parquet ./data/seed/
COPY data/fx_rates.csv ./data/

RUN useradd --create-home appuser && mkdir -p /srv/var && chown appuser /srv/var
USER appuser

EXPOSE 8000
# Migrations run before the API accepts traffic (ADR-0003).
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
