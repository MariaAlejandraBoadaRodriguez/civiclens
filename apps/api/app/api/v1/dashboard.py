"""/api/v1/dashboard — executive view of one or several datasets, in CAD (spec M5)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_translator
from app.api.v1.sql import ready_dataset
from app.db.session import get_session
from app.i18n.loader import Translator
from app.services import dashboard as svc

router = APIRouter(prefix="/api/v1", tags=["dashboard"])
SessionDep = Annotated[Session, Depends(get_session)]
TDep = Annotated[Translator, Depends(get_translator)]
MAX_DATASETS = 5


@router.get("/dashboard")
def get_dashboard(
    session: SessionDep,
    t: TDep,
    dataset_id: Annotated[
        list[Annotated[str, Query(min_length=1, max_length=64)]],
        Query(min_length=1, max_length=MAX_DATASETS, description="Dataset id or seed slug"),
    ],
    period: svc.Period = "all",
    category: svc.Category = "all",
) -> dict[str, Any]:
    refs = list(dict.fromkeys(dataset_id))  # keep order, drop repeats
    datasets = [ready_dataset(session, ref) for ref in refs]
    return svc.build(datasets, t, period, category)
