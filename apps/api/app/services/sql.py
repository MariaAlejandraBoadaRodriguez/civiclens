"""SQL Lab orchestration: star schema per dataset (built lazily), guarded queries, KPIs."""

from __future__ import annotations

import logging
import threading
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.core import memory
from app.core.cleaning.ops import apply_steps
from app.core.seed.registry import SEEDS
from app.core.sql import engine
from app.core.sql.kpi_catalog import CATALOG
from app.core.sql.star_schema import GROUPS, build_star
from app.db.models import Dataset, DatasetStatus, Job
from app.i18n.loader import Translator
from app.services import storage
from app.services.cleaning import context, default_currency, load_issues

log = logging.getLogger(__name__)
_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)


def _group_labels() -> dict[str, dict[str, str]]:
    en, es = Translator("en"), Translator("es")
    return {g: {"en": en(f"categories.{g}"), "es": es(f"categories.{g}")} for g in GROUPS}


def jurisdiction(ds: Dataset) -> str:
    seed = SEEDS.get(ds.slug or "")
    return seed.jurisdiction if seed else "CA"


def source_frame(ds: Dataset) -> tuple[Any, str]:
    """The cleaned layer, or — when no recipe was applied yet — the staged layer with the
    recommended recipe applied on the fly. Returns (frame, "clean" | "recommended")."""
    clean = storage.clean_path(ds.id)
    if clean.exists():
        import pandas as pd

        return pd.read_parquet(clean), "clean"
    issues = load_issues(ds)["issues"]
    steps = [s for i in issues for o in i["options"] if o["recommended"] for s in o["steps"]]
    staged = storage.read_parquet(storage.staged_path(ds.id))
    return apply_steps(staged, steps, context()), "recommended"


def ensure_star(ds: Dataset, rebuild: bool = False) -> Path:
    """The dataset's analysis model, built when missing: the typed table ``data`` (every
    dataset) plus, when the Government / procurement pack applies, the star schema in CAD.
    ``rebuild`` replaces an existing file atomically: readers keep querying the old file until
    the new one is in place (deleting it first made concurrent KPI/SQL requests fail while a
    recipe was being applied)."""
    from app.services import analysis

    path = storage.star_path(ds.id)
    if path.exists() and analysis.meta_path(ds).exists() and not rebuild:
        return path
    with _locks[str(ds.id)]:
        if path.exists() and analysis.meta_path(ds).exists() and not rebuild:
            return path
        frame, origin = source_frame(ds)
        profile = storage.read_json(storage.profile_path(ds.id))
        typed, metas, canonical = analysis.build(frame, profile)
        from app.core import packs as pack_engine

        suggestions = pack_engine.suggestions(metas, canonical)
        star = None
        if analysis.stored_pack_engine(ds, suggestions) == "procurement_star":
            star = build_star(
                frame, jurisdiction(ds), context().fx, _group_labels(), default_currency(ds)
            )
        del frame
        write_model(path, typed, metas, star)
        del typed
        storage.write_json({"origin": origin, "star": star is not None}, path.with_suffix(".json"))
        analysis.finish_model(ds, path, metas, canonical, origin)
        log.info(
            "model for %s built from %s data (star schema: %s)", ds.id, origin, star is not None
        )
    memory.release()
    return path


def write_model(path: Path, typed: Any, metas: list[Any], star: Any | None) -> None:
    """One DuckDB file: ``data`` and, for procurement, the star-schema tables (atomic replace)."""
    import duckdb

    from app.services import analysis

    tmp = path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp))
    try:
        analysis.write_data_table(con, typed, metas)
        if star is not None:
            for name, df in star.tables().items():
                con.register("_df", df)
                con.execute(f"CREATE TABLE {name} AS SELECT * FROM _df")  # noqa: S608 — fixed names
                con.unregister("_df")
    finally:
        con.close()
    tmp.replace(path)


def has_star(ds: Dataset) -> bool:
    ensure_star(ds)
    meta = storage.read_json(storage.star_path(ds.id).with_suffix(".json")) or {}
    return bool(meta.get("star"))


def star_origin(ds: Dataset) -> str:
    meta = storage.read_json(storage.star_path(ds.id).with_suffix(".json")) or {}
    return meta.get("origin", "recommended")


def run_query(ds: Dataset, sql: str) -> engine.QueryResult:
    return engine.run(ensure_star(ds), sql)


def kpis(ds: Dataset, t: Translator) -> list[dict[str, Any]]:
    path = ensure_star(ds)
    out = []
    for k in CATALOG:
        value = engine.run(path, k.sql).rows[0][0]
        out.append(
            {
                "kpi_id": k.kpi_id,
                "value": None if value is None else round(float(value), 6),
                "unit": k.unit,
                "currency": "CAD" if k.unit == "currency" else None,
                "owner": k.owner,
                "formula_sql": k.sql,
                "name": t(f"kpi_catalog.{k.kpi_id}.name"),
                "definition": t(f"kpi_catalog.{k.kpi_id}.definition"),
            }
        )
    quality = (ds.profile_json or {}).get("quality_after") or {}
    score = quality.get("score", ds.quality_score)
    out.append(
        {
            "kpi_id": "quality_score",
            "value": None if score is None else float(score),
            "unit": "score",
            "currency": None,
            "owner": "data",
            "formula_sql": None,
            "name": t("kpi_catalog.quality_score.name"),
            "definition": t("kpi_catalog.quality_score.definition"),
        }
    )
    return out


def run_star_phase(job_id: uuid.UUID) -> None:
    """Last phase of ingest and apply jobs (own process in production): build the star schema
    here, so no SQL Lab request ever has to, then mark the dataset usable and the job done."""
    from app.core.jobs import run_phase

    def work(session: Any, job: Job, ds: Dataset) -> None:
        ensure_star(ds, rebuild=True)
        from app.services import ml  # model results described the previous star schema

        ml.invalidate_results(ds)
        if ds.status == DatasetStatus.UPLOADED:
            ds.status = DatasetStatus.PROFILED

    from app.core.jobs import report_progress

    report_progress(job_id, "building_model")
    run_phase(job_id, "job.crashed", work, finish=True)


BI_FORMATS = ("csv", "parquet")


def export_star(ds: Dataset, fmt: str) -> bytes:
    """The model as a zip of one file per table, for Power BI / Tableau (spec M5): ``data``
    always, the star schema for procurement data.
    Read through the guarded read-only connection; written in memory (the tables are small)."""
    import io
    import zipfile

    import pyarrow.csv as pa_csv
    import pyarrow.parquet as pq

    from app.core.sql.star_schema import TABLES

    if fmt not in BI_FORMATS:
        raise ValueError(fmt)
    buffer = io.BytesIO()
    con = engine.connect(ensure_star(ds))
    try:
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            names = ["data"] + (list(TABLES) if has_star(ds) else [])
            for name in names:
                rel = con.sql(f"SELECT * FROM {name}")  # noqa: S608 — fixed table names
                # DuckDB 2 renamed the relation's arrow() to to_arrow_table().
                fetch = getattr(rel, "to_arrow_table", None) or rel.arrow
                table = fetch()
                out = io.BytesIO()
                if fmt == "csv":
                    pa_csv.write_csv(table, out)
                else:
                    pq.write_table(table, out, compression="zstd")
                zf.writestr(f"{name}.{fmt}", out.getvalue())
            zf.writestr("README.txt", BI_README)
    finally:
        con.close()
    memory.release()
    return buffer.getvalue()


BI_README = """CivicLens model export

data           every dataset: the cleaned columns of the file, typed, with safe snake_case names
fact_contract  one row per contract; amount_cad is the amount converted to CAD with the
               rate of the signing month; joins: entity_id, supplier_id, date_id, category_id
dim_entity     buying entities
dim_supplier   suppliers (first_seen = first signing date)
dim_date       calendar and fiscal year of the jurisdiction
dim_category   goods / services / construction / other, with EN and ES labels
dim_currency   currencies present in the source

Load guide: https://github.com/MariaAlejandraBoadaRodriguez/civiclens/blob/main/docs/bi-export.md
"""
