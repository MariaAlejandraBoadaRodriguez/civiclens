"""/api/v1 SQL Lab — star schema, guarded read-only queries, guided queries, KPIs (slice 5c)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_translator
from app.api.headers import content_disposition
from app.api.problems import ProblemError
from app.core.sql import engine
from app.core.sql.guard import MAX_SQL_CHARS, QueryRejected
from app.core.sql.guided import GUIDED
from app.db.models import Dataset, DatasetStatus
from app.db.session import get_session
from app.i18n.loader import Translator
from app.services import analysis
from app.services import datasets as datasets_svc
from app.services import sql as svc

router = APIRouter(prefix="/api/v1", tags=["sql"])
SessionDep = Annotated[Session, Depends(get_session)]
TDep = Annotated[Translator, Depends(get_translator)]


class QueryRequest(BaseModel):
    dataset_id: str = Field(description="Dataset id (UUID) or seed slug")
    sql: str = Field(description=f"One SELECT/WITH statement, at most {MAX_SQL_CHARS} characters")


def ready_dataset(session: Session, ref: str) -> Dataset:
    ds = datasets_svc.resolve(session, ref)
    if ds is None:
        raise ProblemError(404, "dataset.not_found", dataset_id=ref)
    if ds.status not in (DatasetStatus.PROFILED, DatasetStatus.CLEANED):
        raise ProblemError(409, "dataset.not_ready")
    return ds


def procurement_dataset(session: Session, ref: str) -> Dataset:
    """A ready dataset whose model has the procurement star schema (Government pack); other
    datasets get a clear 409 instead of a failure deep inside a procurement-only view."""
    ds = ready_dataset(session, ref)
    if not svc.has_star(ds):
        raise ProblemError(409, "domain.procurement_only")
    return ds


def _guardrails() -> dict[str, Any]:
    return {"read_only": True, "timeout_s": int(engine.TIMEOUT_S), "max_rows": engine.MAX_ROWS}


@router.get("/datasets/{dataset_id}/schema")
def get_schema(dataset_id: str, session: SessionDep, t: TDep) -> dict[str, Any]:
    """Tables of the dataset's model: ``data`` (every dataset: the cleaned columns, typed, with
    safe names) and, for the Government / procurement pack, the star schema. Built on first use
    from the cleaned data (or from the recommended recipe when none was applied yet)."""
    ds = ready_dataset(session, dataset_id)
    tables = engine.describe(svc.ensure_star(ds))
    for table in tables:
        name = table["name"]
        table["role"] = (
            "data" if name == "data" else "fact" if name.startswith("fact_") else "dimension"
        )
    tables.sort(key=lambda tb: (tb["role"] != "data", tb["role"] != "fact", tb["name"]))
    meta = analysis.load_meta(ds)
    return {
        "dataset_id": str(ds.id),
        "origin": svc.star_origin(ds),
        "tables": tables,
        "data_columns": [
            {
                "name": c["name"],
                "source": c["source"],
                "kind": c["kind"],
                "kind_label": t(f"analysis.kinds.{c['kind']}"),
                "sql_type": c["sql_type"],
                "binary": c["binary"],
                "nulls": c["nulls"],
                "distinct": c["distinct"],
                "examples": c["examples"],
            }
            for c in meta.get("columns", [])
        ],
        "domain": analysis.domain(ds, meta),
        "guardrails": _guardrails(),
    }


@router.post("/query")
def run_query(body: QueryRequest, session: SessionDep) -> dict[str, Any]:
    ds = ready_dataset(session, body.dataset_id)
    try:
        result = svc.run_query(ds, body.sql)
    except QueryRejected as exc:
        status = 408 if exc.code == "sql.timeout" else 400
        raise ProblemError(status, exc.code, **exc.params) from exc
    return {
        "columns": result.columns,
        "rows": result.rows,
        "row_count": result.row_count,
        "truncated": result.truncated,
        "elapsed_ms": result.elapsed_ms,
    }


@router.get("/guided-queries")
def list_guided(
    session: SessionDep,
    t: TDep,
    dataset_id: Annotated[
        str | None, Query(max_length=64, description="Dataset id or seed slug")
    ] = None,
) -> dict[str, Any]:
    """With ``dataset_id``: questions for that file — the domain pack's questions (its goal's
    first), then questions generated from its own columns, then (procurement only) the 12
    procurement questions on the star schema. Without it: the procurement questions."""
    procurement = [
        {
            "query_id": q.query_id,
            "concepts": list(q.concepts),
            "sql": q.sql,
            "source": "government",
            "goals": [],
            "title": t(f"guided.{q.query_id}.title"),
            "question": t(f"guided.{q.query_id}.question"),
            "explanation": t(f"guided.{q.query_id}.explanation"),
        }
        for q in GUIDED
    ]
    if dataset_id is None:
        items = procurement
    else:
        ds = ready_dataset(session, dataset_id)
        svc.ensure_star(ds)
        items = analysis.guided(ds, t)
        if svc.has_star(ds):
            items = procurement + items
    return {"items": items, "guardrails": _guardrails()}


@router.get("/kpis/{dataset_id}")
def get_kpis(dataset_id: str, session: SessionDep, t: TDep) -> dict[str, Any]:
    ds = ready_dataset(session, dataset_id)
    svc.ensure_star(ds)  # builds the model first, so the origin below is known
    if svc.has_star(ds):
        items = svc.kpis(ds, t)
    else:
        items = analysis.pack_kpis(ds, t) + analysis.generic_kpis(ds, t)
    return {"dataset_id": str(ds.id), "origin": svc.star_origin(ds), "items": items}


@router.get("/datasets/{dataset_id}/export", tags=["sql"])
def export_star_schema(
    dataset_id: str,
    session: SessionDep,
    format: Literal["csv", "parquet"] = "csv",  # noqa: A002
) -> Response:
    """The model as a zip (one file per table) for Power BI / Tableau: ``data`` for every
    dataset, plus the star-schema tables for procurement data."""
    ds = ready_dataset(session, dataset_id)
    body = svc.export_star(ds, format)
    name = f"civiclens-star-{ds.slug or ds.id}-{format}.zip"
    return Response(
        body,
        media_type="application/zip",
        headers={"Content-Disposition": content_disposition("attachment", name)},
    )
