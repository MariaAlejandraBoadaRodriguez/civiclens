"""/api/v1/keys — agency API keys, for the single admin only (US-24, slice 5e)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.problems import ProblemError
from app.api.security import forget_key, require_admin
from app.core import keys
from app.db.models import ApiKey, AuditLog
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/keys", tags=["admin"])
SessionDep = Annotated[Session, Depends(get_session)]
AdminDep = Annotated[str, Depends(require_admin)]
Scope = Literal["datasets:write", "recipes:write", "models:run", "reports:read"]


class KeyInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[Scope] = Field(min_length=1)


def key_out(row: ApiKey) -> dict[str, Any]:
    iso = lambda d: d.isoformat() if d else None  # noqa: E731
    return {
        "id": str(row.id),
        "name": row.name,
        "prefix": row.prefix,
        "scopes": list(row.scopes or []),
        "created_at": iso(row.created_at),
        "last_used_at": iso(row.last_used_at),
        "revoked_at": iso(row.revoked_at),
    }


@router.get("")
def list_keys(session: SessionDep, _: AdminDep) -> dict[str, Any]:
    """Never returns a secret, only the public prefix."""
    rows = session.scalars(select(ApiKey).order_by(ApiKey.created_at.desc())).all()
    return {"items": [key_out(r) for r in rows]}


@router.post("", status_code=201)
def create_key(body: KeyInput, session: SessionDep, admin: AdminDep) -> dict[str, Any]:
    """The full key is returned once, in this response; only its argon2 hash is stored."""
    full, prefix = keys.generate()
    row = ApiKey(
        name=body.name, prefix=prefix, hash=keys.hash_key(full), scopes=sorted(set(body.scopes))
    )
    session.add(row)
    session.flush()
    session.add(
        AuditLog(
            actor=admin,
            action="api_key.created",
            target=f"api_key:{row.id}",
            details_json={"name": row.name, "prefix": prefix, "scopes": row.scopes},
        )
    )
    session.commit()
    return {**key_out(row), "key": full}


@router.delete("/{key_id}", status_code=204)
def revoke_key(key_id: str, session: SessionDep, admin: AdminDep) -> Response:
    """Sets ``revoked_at``: the key stops working on the next request."""
    try:
        row = session.get(ApiKey, uuid.UUID(key_id))
    except ValueError:
        row = None
    if row is None:
        raise ProblemError(404, "api_key.not_found", key_id=key_id)
    if row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        session.add(
            AuditLog(
                actor=admin,
                action="api_key.revoked",
                target=f"api_key:{row.id}",
                details_json={"prefix": row.prefix},
            )
        )
        session.commit()
    forget_key(row.id)
    return Response(status_code=204)
