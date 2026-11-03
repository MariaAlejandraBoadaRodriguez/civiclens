"""/api/v1/recipes — save, read, preview and export cleaning recipes (slice 5b)."""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.headers import content_disposition
from app.api.problems import ProblemError, iso_utc, only_methods
from app.api.security import require_scope
from app.core.cleaning.recipe import RecipeError, validate_steps
from app.db.models import Recipe
from app.db.session import get_session
from app.services import cleaning, storage

router = APIRouter(prefix="/api/v1/recipes", tags=["cleaning"])
SessionDep = Annotated[Session, Depends(get_session)]


class Step(BaseModel):
    op: str
    args: dict[str, Any] = Field(default_factory=dict)


class RecipeInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    dataset_id: uuid.UUID | None = None
    steps: list[Step]


class PreviewInput(BaseModel):
    steps: list[Step]
    columns: list[str] = Field(
        default_factory=list, description="Staged columns, for the SQL export"
    )
    name: str = "recipe"


def validated(steps: list[Step]) -> list[dict[str, Any]]:
    try:
        return validate_steps([s.model_dump() for s in steps])
    except RecipeError as exc:
        raise ProblemError(422, exc.code, step=(exc.step or 0) + 1, message=str(exc)) from exc


def recipe_out(recipe: Recipe) -> dict[str, Any]:
    return {
        "id": str(recipe.id),
        "name": recipe.name,
        "version": recipe.version,
        "dataset_id": str(recipe.dataset_id) if recipe.dataset_id else None,
        "steps": recipe.steps_json,
        "created_at": iso_utc(recipe.created_at),
    }


@router.post("", status_code=201, dependencies=[Depends(require_scope("recipes:write"))])
def create_recipe(body: RecipeInput, session: SessionDep) -> dict[str, Any]:
    steps = validated(body.steps)
    recipe = cleaning.save_recipe(session, body.name, steps, body.dataset_id)
    return recipe_out(recipe)


@router.get("/preview", include_in_schema=False)
def preview_wrong_method() -> None:
    """Only POST exists here; without this, GET would read "preview" as a recipe id."""
    raise StarletteHTTPException(405)


only_methods(f"{router.prefix}/preview", ["POST"])


@router.post("/preview")
def preview_recipe(body: PreviewInput) -> dict[str, str]:
    """Code for the live recipe panel: pandas pipeline, DuckDB SQL and the JSON document."""
    validated(body.steps)
    return cleaning.code_preview([s.model_dump() for s in body.steps], body.columns, body.name)


def _get(session: Session, recipe_id: str) -> Recipe:
    try:
        recipe = session.get(Recipe, uuid.UUID(recipe_id))
    except ValueError:
        recipe = None
    if recipe is None:
        raise ProblemError(404, "recipe.not_found", recipe_id=recipe_id)
    return recipe


@router.get("/{recipe_id}")
def get_recipe(recipe_id: str, session: SessionDep) -> dict[str, Any]:
    return recipe_out(_get(session, recipe_id))


@router.get("/{recipe_id}/export", response_class=PlainTextResponse)
def export_recipe(
    recipe_id: str, session: SessionDep, format: Literal["pandas", "sql", "json"] = "pandas"
) -> PlainTextResponse:
    recipe = _get(session, recipe_id)
    columns: list[str] = []
    if recipe.dataset_id:
        cached = storage.read_json(storage.issues_path(recipe.dataset_id))
        columns = (cached or {}).get("columns", [])
    text = cleaning.export(recipe, format, columns)
    ext = {"pandas": "py", "sql": "sql", "json": "json"}[format]
    media = {"pandas": "text/x-python", "sql": "application/sql", "json": "application/json"}[
        format
    ]
    filename = f"{recipe.name.replace(' ', '_')}_v{recipe.version}.{ext}"
    return PlainTextResponse(
        text,
        media_type=media,
        headers={"Content-Disposition": content_disposition("attachment", filename)},
    )
