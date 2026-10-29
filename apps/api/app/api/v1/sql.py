"""/api/v1 SQL Lab — star schema, guarded read-only queries, guided queries, KPIs (slice 5c)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_translator
from app.api.problems import ProblemError
from app.core.sql import engine
from app.core.sql.guard import MAX_SQL_CHARS, QueryRejected
from app.core.sql.guided import GUIDED
from app.db.models import Dataset, DatasetStatus
from app.db.session import get_session
from app.i18n.loader import Translator
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


def _guardrails() -> dict[str, Any]:
    return {"read_only": True, "timeout_s": int(engine.TIMEOUT_S), "max_rows": engine.MAX_ROWS}


@router.get("/datasets/{dataset_id}/schema")
def get_schema(dataset_id: str, session: SessionDep) -> dict[str, Any]:
    """Star schema tables, columns and row counts. Built on first use from the cleaned data
    (or from the recommended recipe when none was applied yet)."""
    ds = ready_dataset(session, dataset_id)
    tables = engine.describe(svc.ensure_star(ds))
    for table in tables:
        table["role"] = "fact" if table["name"].startswith("fact_") else "dimension"
    return {
        "dataset_id": str(ds.id),
        "origin": svc.star_origin(ds),
        "tables": tables,
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
def list_guided(t: TDep) -> dict[str, Any]:
    return {
        "items": [
            {
                "query_id": q.query_id,
                "concepts": list(q.concepts),
                "sql": q.sql,
                "title": t(f"guided.{q.query_id}.title"),
                "question": t(f"guided.{q.query_id}.question"),
                "explanation": t(f"guided.{q.query_id}.explanation"),
            }
            for q in GUIDED
        ],
        "guardrails": _guardrails(),
    }


@router.get("/kpis/{dataset_id}")
def get_kpis(dataset_id: str, session: SessionDep, t: TDep) -> dict[str, Any]:
    ds = ready_dataset(session, dataset_id)
    items = svc.kpis(ds, t)  # builds the star schema first, so the origin below is known
    return {"dataset_id": str(ds.id), "origin": svc.star_origin(ds), "items": items}
