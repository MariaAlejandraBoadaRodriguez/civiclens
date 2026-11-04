"""/api/v1/datasets/{id}/overview and /chart — the dashboard for any table (generic core).

The overview is the strong default: KPI tiles (domain pack first), quality before → after and
chart sections that each come with a written finding in the UI language. ``/chart`` answers a
chart the user configures: metric, aggregation, dimension, filters and chart type.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_translator
from app.api.problems import ProblemError
from app.api.v1.sql import ready_dataset
from app.core.sql.guard import QueryRejected
from app.db.session import get_session
from app.i18n.loader import Translator
from app.services import overview as svc

router = APIRouter(prefix="/api/v1/datasets", tags=["dashboard"])
SessionDep = Annotated[Session, Depends(get_session)]
TDep = Annotated[Translator, Depends(get_translator)]


class ChartFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    column: str = Field(min_length=1, max_length=200)
    op: Literal["eq", "ne", "gte", "lte", "in"] = "eq"
    values: list[str | float] = Field(default_factory=list, max_length=50)


class ChartSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dimension: str = Field(min_length=1, max_length=200, description="Column to group by")
    aggregation: Literal["count", "sum", "avg", "median", "min", "max"] = "count"
    metric: str | None = Field(default=None, max_length=200, description="Numeric column")
    grain: Literal["year", "month", "day"] | None = None
    filters: list[ChartFilter] = Field(default_factory=list, max_length=5)
    chart_type: Literal["bar", "line", "table"] = "bar"


@router.get("/{dataset_id}/overview")
def get_overview(dataset_id: str, session: SessionDep, t: TDep) -> dict[str, Any]:
    ds = ready_dataset(session, dataset_id)
    return svc.overview(ds, t)


@router.post("/{dataset_id}/chart")
def post_chart(dataset_id: str, body: ChartSpec, session: SessionDep) -> dict[str, Any]:
    ds = ready_dataset(session, dataset_id)
    from app.services import sql as sql_svc

    sql_svc.ensure_star(ds)
    try:
        return svc.chart(ds, body.model_dump())
    except svc.ChartError as exc:
        raise ProblemError(422, exc.code, **exc.params) from exc
    except QueryRejected as exc:  # the read-only guard refused it: nothing ran
        status = 408 if exc.code == "sql.timeout" else 400
        raise ProblemError(status, exc.code, **exc.params) from exc
