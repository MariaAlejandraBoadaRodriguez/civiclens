"""/api/v1/datasets/{id}/domain — the domain pack, analysis goal and column-role mapping.

After ingest CivicLens suggests a pack (with a fit score) and a mapping of the pack's semantic
roles to the file's columns (each with a confidence). The user confirms or edits the choice
here. Switching to or from the Government / procurement pack rebuilds the model (the star
schema exists only for that pack) in a background job; any other change applies at once.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_translator
from app.api.problems import ProblemError
from app.api.security import Principal, require_scope
from app.api.v1.sql import ready_dataset
from app.core import jobs
from app.core import packs as pack_engine
from app.db.models import Dataset, Job, JobStatus, JobType
from app.db.session import get_session
from app.i18n.loader import Translator
from app.services import analysis
from app.services import sql as sql_svc

router = APIRouter(prefix="/api/v1/datasets", tags=["datasets"])
SessionDep = Annotated[Session, Depends(get_session)]
TDep = Annotated[Translator, Depends(get_translator)]


class RoleChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    column: str = Field(min_length=1, max_length=200, description="Column of table `data`")
    positive: str | None = Field(
        default=None, max_length=200, description="Target roles: the value that means 'yes'"
    )


class DomainChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pack: str = Field(min_length=1, max_length=40)
    goal: str | None = Field(default=None, max_length=40)
    roles: dict[str, RoleChoice] | None = Field(
        default=None, description="Omit to accept the suggested mapping for this pack"
    )


def domain_out(ds: Dataset, t: Translator) -> dict[str, Any]:
    meta = analysis.load_meta(ds)
    by_name = {c["name"]: c for c in meta.get("columns", [])}
    active = analysis.domain(ds, meta)
    roles = {
        role_id: {
            "column": entry["column"],
            "source": by_name[entry["column"]]["source"],
            "confidence": entry.get("confidence"),
            "positive": entry.get("positive"),
        }
        for role_id, entry in active["roles"].items()
        if entry.get("column") in by_name
    }
    return {
        "dataset_id": str(ds.id),
        "pack": active["pack"],
        "goal": active["goal"],
        "confirmed": active["confirmed"],
        "roles": roles,
        "suggestions": [
            {"pack": s["pack"], "score": s["score"], "name": t(f"packs.{s['pack']}.name")}
            for s in meta.get("suggestions", [])
        ],
        "packs": analysis.pack_catalog(t),
        "columns": [
            {
                "name": c["name"],
                "source": c["source"],
                "kind": c["kind"],
                "kind_label": t(f"analysis.kinds.{c['kind']}"),
                "binary": bool(c["binary"]) and c["distinct"] == 2,
                "examples": c["examples"],
                "top": [v["value"] for v in c.get("top", [])],
            }
            for c in meta.get("columns", [])
        ],
        "job": None,
    }


@router.get("/{dataset_id}/domain")
def get_domain(dataset_id: str, session: SessionDep, t: TDep) -> dict[str, Any]:
    ds = ready_dataset(session, dataset_id)
    sql_svc.ensure_star(ds)
    return domain_out(ds, t)


@router.put("/{dataset_id}/domain")
def put_domain(
    dataset_id: str,
    body: DomainChoice,
    background: BackgroundTasks,
    session: SessionDep,
    t: TDep,
    caller: Annotated[Principal, Depends(require_scope("recipes:write"))],
) -> dict[str, Any]:
    ds = ready_dataset(session, dataset_id)
    if ds.slug:
        raise ProblemError(409, "domain.seed_fixed")
    sql_svc.ensure_star(ds)
    meta = analysis.load_meta(ds)
    pack = pack_engine.packs().get(body.pack)
    if pack is None:
        raise ProblemError(422, "domain.unknown_pack", pack=body.pack)
    suggestion = next((s for s in meta.get("suggestions", []) if s["pack"] == pack.id), None)
    if pack.engine == "procurement_star" and not (suggestion and suggestion["score"] > 0):
        raise ProblemError(409, "domain.not_applicable", pack=pack.id)
    goal = body.goal or pack.default_goal
    if not any(g["id"] == goal for g in pack.goals):
        raise ProblemError(422, "domain.unknown_goal", goal=goal)
    columns = {c["name"] for c in meta.get("columns", [])}
    if body.roles is None:
        roles = (suggestion or {}).get("roles", {})
    else:
        roles = {}
        for role_id, choice in body.roles.items():
            if pack.role(role_id) is None:
                raise ProblemError(422, "domain.unknown_role", role=role_id)
            if choice.column not in columns:
                raise ProblemError(422, "domain.unknown_column", column=choice.column)
            suggested = ((suggestion or {}).get("roles", {}).get(role_id)) or {}
            # Confirming the suggested column keeps its confidence; another column is the user's.
            same = suggested.get("column") == choice.column
            roles[role_id] = {
                "column": choice.column,
                "confidence": suggested.get("confidence", 1.0) if same else 1.0,
            }
            if choice.positive is not None:
                roles[role_id]["positive"] = choice.positive
            elif pack.role(role_id).target and same and suggested.get("positive") is not None:
                roles[role_id]["positive"] = suggested["positive"]
        if len({e["column"] for e in roles.values()}) < len(roles):
            raise ProblemError(422, "domain.column_reused")
    had_star = sql_svc.has_star(ds)
    profile = dict(ds.profile_json or {})
    profile["domain"] = {"pack": pack.id, "goal": goal, "roles": roles, "confirmed": True}
    ds.profile_json = profile  # a new dict, so the JSON column is marked as changed
    session.commit()
    out = domain_out(ds, t)
    if had_star != (pack.engine == "procurement_star"):
        job = Job(
            type=JobType.BUILD_SCHEMA,
            status=JobStatus.QUEUED,
            dataset_id=ds.id,
            api_key_id=caller.key_id,
            input_json={"reason": "domain", "pack": pack.id},
        )
        session.add(job)
        session.commit()
        background.add_task(jobs.run, jobs.BUILD_SCHEMA, job.id)
        out["job"] = {"id": str(job.id), "status": job.status.value}
    return out
