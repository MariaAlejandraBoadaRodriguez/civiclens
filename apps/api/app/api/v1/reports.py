"""/api/v1/reports — executive report in the requested language (US-05, slice 5e)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.api.problems import ProblemError
from app.api.security import current_principal
from app.api.v1.sql import ready_dataset
from app.db.session import get_session
from app.i18n.loader import SUPPORTED
from app.services import reports

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/{dataset_id}", response_class=HTMLResponse)
def get_report(
    dataset_id: str,
    request: Request,
    session: SessionDep,
    lang: Annotated[Literal["en", "es"] | None, Query()] = None,
    format: Annotated[Literal["html", "pdf"], Query()] = "html",  # noqa: A002 — public param name
) -> HTMLResponse:
    """``lang`` wins over ``Accept-Language``. Open to anonymous callers; a key needs
    ``reports:read``."""
    principal = current_principal(request)
    if principal.kind == "key" and "reports:read" not in principal.scopes:
        raise ProblemError(403, "auth.insufficient_scope", scope="reports:read")
    language = lang or request.state.t.lang
    if language not in SUPPORTED:
        language = "en"
    ds = ready_dataset(session, dataset_id)
    if format == "pdf":
        raise ProblemError(406, "report.pdf_unavailable")
    html = reports.render_html(ds, language)
    name = f"civiclens-report-{ds.slug or ds.id}-{language}.html"
    return HTMLResponse(
        html,
        headers={
            "Content-Language": language,
            "Content-Disposition": f'inline; filename="{name}"',
        },
    )
