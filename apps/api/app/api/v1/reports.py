"""/api/v1/reports — executive report in the requested language (US-05, slice 5e)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.api.headers import content_disposition
from app.api.problems import ProblemError
from app.api.security import current_principal
from app.api.v1.sql import procurement_dataset
from app.core.observability import REPORT_CSP
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
) -> Response:
    """``lang`` wins over ``Accept-Language``. Open to anonymous callers; a key needs
    ``reports:read``."""
    principal = current_principal(request)
    if principal.kind == "key" and "reports:read" not in principal.scopes:
        raise ProblemError(403, "auth.insufficient_scope", scope="reports:read")
    language = lang or request.state.t.lang
    if language not in SUPPORTED:
        language = "en"
    ds = procurement_dataset(session, dataset_id)
    slug = ds.slug or ds.id
    headers = {"Content-Language": language}
    if format == "pdf":
        name = f"civiclens-report-{slug}-{language}.pdf"
        headers["Content-Disposition"] = content_disposition("inline", name)
        return Response(
            reports.render_pdf(ds, language), media_type="application/pdf", headers=headers
        )
    name = f"civiclens-report-{slug}-{language}.html"
    headers["Content-Disposition"] = content_disposition("inline", name)
    headers["Content-Security-Policy"] = REPORT_CSP  # self-contained page: no scripts at all
    return HTMLResponse(reports.render_html(ds, language), headers=headers)
