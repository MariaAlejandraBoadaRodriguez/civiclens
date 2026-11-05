"""Generic analysis of any dataset: the typed ``data`` table, its column metadata, the domain
pack (suggested, then confirmed by the user) with its role mapping, guided questions and KPIs.

``analysis.json`` next to the model file holds what the web app needs without touching DuckDB:
the columns (name, header, kind, examples …), the validated questions and the pack suggestions.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from app.core import packs as pack_engine
from app.core.analysis.questions import generate
from app.core.analysis.table import ColumnMeta, build_table, for_duckdb
from app.core.sql import engine
from app.core.sql.guard import QueryRejected
from app.db.models import Dataset
from app.i18n.loader import Translator
from app.services import storage

log = logging.getLogger(__name__)
GENERAL = "general"


def meta_path(ds: Dataset):
    return storage.star_path(ds.id).with_name("analysis.json")


def frame_names(
    profile: dict[str, Any] | None,
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """For each column of the staged/clean layer: its profiler type hint, its header as written
    in the file, and its canonical procurement field (if mapped)."""
    hints: dict[str, str] = {}
    sources: dict[str, str] = {}
    canonical: dict[str, str] = {}
    used: set[str] = set()
    for c in (profile or {}).get("columns_profile", []):
        target = c["canonical_field"] or c["source_header"]
        if target in used:
            target = f"{target}__{c['source_header']}"
        used.add(target)
        hints[target] = c.get("inferred_type")
        sources[target] = c["source_header"]
        if c["canonical_field"]:
            canonical[target] = c["canonical_field"]
    return hints, sources, canonical


def build(
    frame: pd.DataFrame, profile: dict[str, Any] | None
) -> tuple[pd.DataFrame, list[ColumnMeta], dict[str, str]]:
    """Typed table + column metadata + canonical field → ``data`` column name."""
    hints, sources, canonical = frame_names(profile)
    typed, metas = build_table(frame, hints, sources)
    by_source = {m.source: m.name for m in metas}
    canonical_cols = {
        field: by_source[sources[col]]
        for col, field in canonical.items()
        if sources[col] in by_source
    }
    return typed, metas, canonical_cols


def write_data_table(con, typed: pd.DataFrame, metas: list[ColumnMeta]) -> None:
    """``data`` with the declared SQL type of every column (inside an open DuckDB connection)."""
    df = for_duckdb(typed, metas)
    con.register("_data", df)
    select = ", ".join(f'CAST("{m.name}" AS {m.sql_type}) AS "{m.name}"' for m in metas) or "*"
    con.execute(f"CREATE TABLE data AS SELECT {select} FROM _data")  # noqa: S608 — safe names
    con.unregister("_data")


def finish_model(
    ds: Dataset, path, metas: list[ColumnMeta], canonical: dict[str, str], origin: str
) -> None:
    """Validate the generated questions against the new file and store the metadata."""
    rows = metas[0].rows if metas else 0
    questions = []
    for question in generate(metas, rows):
        try:
            engine.run(path, question.sql, timeout_s=5)
            questions.append(question.to_dict())
        except QueryRejected as exc:
            log.warning("dropping generated question %s: %s", question.query_id, exc.params)
    storage.write_json(
        {
            "origin": origin,
            "rows": rows,
            "columns": [m.to_dict() for m in metas],
            "canonical": canonical,
            "questions": questions,
            "suggestions": pack_engine.suggestions(metas, canonical),
        },
        meta_path(ds),
    )


def load_meta(ds: Dataset) -> dict[str, Any]:
    from app.services.sql import ensure_star

    path = meta_path(ds)
    if not path.exists():
        ensure_star(ds)
    return storage.read_json(path) or {"columns": [], "questions": [], "suggestions": [], "rows": 0}


def columns(ds: Dataset) -> list[ColumnMeta]:
    fields = ColumnMeta.__dataclass_fields__
    return [
        ColumnMeta(**{k: v for k, v in c.items() if k in fields}) for c in load_meta(ds)["columns"]
    ]


# --------------------------------------------------------------------------- domain pack


def suggested_pack(suggestions: list[dict[str, Any]]) -> dict[str, Any]:
    best = suggestions[0] if suggestions else {"pack": GENERAL, "score": 0.3, "roles": {}}
    return (
        best
        if best["score"] > 0.3
        else next(
            (s for s in suggestions if s["pack"] == GENERAL),
            {"pack": GENERAL, "score": 0.3, "roles": {}},
        )
    )


def domain(ds: Dataset, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """The active pack, goal and role mapping: the user's confirmed choice, else the suggestion."""
    stored = (ds.profile_json or {}).get("domain") or {}
    suggestions = (meta or load_meta(ds)).get("suggestions", [])
    if stored.get("pack") in pack_engine.packs():
        pack = pack_engine.packs()[stored["pack"]]
        goal = (
            stored.get("goal")
            if any(g["id"] == stored.get("goal") for g in pack.goals)
            else pack.default_goal
        )
        return {
            "pack": pack.id,
            "goal": goal,
            "roles": stored.get("roles", {}),
            "confirmed": True,
            "engine": pack.engine,
        }
    best = suggested_pack(suggestions)
    pack = pack_engine.packs()[best["pack"]]
    return {
        "pack": pack.id,
        "goal": pack.default_goal,
        "roles": best.get("roles", {}),
        "confirmed": False,
        "engine": pack.engine,
    }


def stored_pack_engine(ds: Dataset, meta_suggestions: list[dict[str, Any]]) -> str:
    """Engine of the pack that applies (used while the model is built)."""
    stored = (ds.profile_json or {}).get("domain") or {}
    if stored.get("pack") in pack_engine.packs():
        return pack_engine.packs()[stored["pack"]].engine
    return pack_engine.packs()[suggested_pack(meta_suggestions)["pack"]].engine


def is_procurement(ds: Dataset) -> bool:
    return domain(ds)["engine"] == "procurement_star"


def _metas_by_name(ds: Dataset) -> dict[str, ColumnMeta]:
    return {m.name: m for m in columns(ds)}


def pack_questions(ds: Dataset) -> list[dict[str, Any]]:
    """The active pack's questions whose roles are mapped, the goal's own questions first."""
    d = domain(ds)
    pack = pack_engine.packs()[d["pack"]]
    metas = _metas_by_name(ds)
    path = storage.star_path(ds.id)
    out = []
    for item in pack.questions:
        if not pack_engine.requires_ok(item, d["roles"], metas):
            continue
        try:
            sql = pack_engine.render(item["sql"], d["roles"], metas, pack).strip()
            engine.run(path, sql, timeout_s=5)
        except (pack_engine.MissingRole, QueryRejected):
            continue
        out.append(
            {
                "query_id": f"{pack.id}.{item['id']}",
                "kind": f"pack.{pack.id}.{item['id']}",
                "sql": sql,
                "params": {
                    r: metas[e["column"]].source
                    for r, e in d["roles"].items()
                    if e.get("column") in metas
                },
                "concepts": item.get("concepts", []),
                "goals": item.get("goals", []),
                "source": pack.id,
            }
        )
    out.sort(key=lambda x: d["goal"] not in x["goals"])
    return out


def localize_question(item: dict[str, Any], t: Translator) -> dict[str, Any]:
    if item["source"] == "generic":
        base = f"analysis.questions.{item['kind']}"
    else:
        pack, qid = item["source"], item["kind"].split(".")[-1]
        base = f"packs.{pack}.questions.{qid}"
    params = {
        **item.get("params", {}),
        "grain": t(f"analysis.grain.{item.get('params', {}).get('grain', 'month')}"),
    }
    return {
        "query_id": item["query_id"],
        "concepts": item.get("concepts", []),
        "sql": item["sql"],
        "source": item["source"],
        "goals": item.get("goals", []),
        "title": t(f"{base}.title", **params),
        "question": t(f"{base}.question", **params),
        "explanation": t(f"{base}.explanation", **params),
    }


def guided(ds: Dataset, t: Translator) -> list[dict[str, Any]]:
    """Pack questions (goal first), then the questions generated from the file's columns."""
    meta = load_meta(ds)
    items = pack_questions(ds) + meta.get("questions", [])
    return [localize_question(i, t) for i in items]


def pack_kpis(ds: Dataset, t: Translator) -> list[dict[str, Any]]:
    d = domain(ds)
    pack = pack_engine.packs()[d["pack"]]
    metas = _metas_by_name(ds)
    path = storage.star_path(ds.id)
    out = []
    for item in pack.kpis:
        if not pack_engine.requires_ok(item, d["roles"], metas):
            continue
        try:
            sql = pack_engine.render(item["sql"], d["roles"], metas, pack)
            value = engine.run(path, sql, timeout_s=5).rows[0][0]
        except (pack_engine.MissingRole, QueryRejected):
            continue
        out.append(
            {
                "kpi_id": f"{pack.id}.{item['id']}",
                "value": None if value is None else round(float(value), 6),
                "unit": item.get("unit", "number"),
                "currency": None,
                "owner": pack.id,
                "formula_sql": sql,
                "name": t(f"packs.{pack.id}.kpis.{item['id']}.name"),
                "definition": t(f"packs.{pack.id}.kpis.{item['id']}.definition"),
            }
        )
    return out


def generic_kpis(ds: Dataset, t: Translator) -> list[dict[str, Any]]:
    """Rows, columns, completeness, quality, then the mean of the main quantities and the rate of
    the target-like flag — meaningful for any table."""
    from app.core.analysis.questions import pick, positive_expr, q

    metas = columns(ds)
    path = storage.star_path(ds.id)
    rows = metas[0].rows if metas else 0
    cells = sum(m.rows for m in metas) or 1
    filled = 1 - sum(m.nulls for m in metas) / cells
    quality = ((ds.profile_json or {}).get("quality_after") or {}).get("score", ds.quality_score)
    out = [
        _kpi("rows", rows, "count", t),
        _kpi("columns", len(metas), "count", t),
        _kpi("completeness", round(filled, 6), "ratio", t),
        _kpi("quality_score", quality, "score", t),
    ]
    p = pick(metas)
    for m in p.numbers[:3]:
        value = engine.run(path, f"SELECT AVG({q(m.name)}) FROM data", timeout_s=5).rows[0][0]  # noqa: S608
        out.append(
            _kpi(
                "mean",
                value,
                "number",
                t,
                column=m.source,
                column_id=m.name,
                formula=f"SELECT AVG({q(m.name)}) FROM data",
            )
        )
    label = next(
        (m for m in p.categories + [m for m in metas if m.kind == "category" and m.distinct > 1]),
        None,
    )
    if label is not None:
        sql = f"SELECT COUNT(DISTINCT {q(label.name)}) FROM data"
        value = engine.run(path, sql, timeout_s=5).rows[0][0]
        out.append(
            _kpi(
                "distinct",
                value,
                "count",
                t,
                column=label.source,
                column_id=label.name,
                formula=sql,
            )
        )
    if p.target is not None:
        sql = f"SELECT AVG(CASE WHEN {positive_expr(p.target)} THEN 1.0 ELSE 0.0 END) FROM data WHERE {q(p.target.name)} IS NOT NULL"  # noqa: S608
        value = engine.run(path, sql, timeout_s=5).rows[0][0]
        out.append(
            _kpi(
                "rate",
                value,
                "ratio",
                t,
                column=p.target.source,
                column_id=p.target.name,
                formula=sql,
            )
        )
    return out


def _kpi(
    kind: str,
    value: Any,
    unit: str,
    t: Translator,
    column: str | None = None,
    column_id: str | None = None,
    formula: str | None = None,
) -> dict[str, Any]:
    return {
        "kpi_id": f"generic.{kind}" + (f".{column_id}" if column_id else ""),
        "value": None if value is None else round(float(value), 6),
        "unit": unit,
        "currency": None,
        "owner": "data",
        "formula_sql": formula,
        "name": t(f"analysis.kpis.{kind}.name", column=column or ""),
        "definition": t(f"analysis.kpis.{kind}.definition", column=column or ""),
    }


# --------------------------------------------------------------------------- packs catalog


def pack_catalog(t: Translator) -> list[dict[str, Any]]:
    out = []
    for pack in pack_engine.packs().values():
        out.append(
            {
                "id": pack.id,
                "name": t(f"packs.{pack.id}.name"),
                "description": t(f"packs.{pack.id}.description"),
                "goals": [
                    {
                        "id": g["id"],
                        "name": t(f"packs.{pack.id}.goals.{g['id']}"),
                        "default": bool(g.get("default")),
                    }
                    for g in pack.goals
                ],
                "roles": [
                    {
                        "id": r.id,
                        "name": t(f"packs.{pack.id}.roles.{r.id}"),
                        "kinds": list(r.kinds),
                        "key": r.key,
                        "target": r.target,
                        "sensitive": r.sensitive,
                    }
                    for r in pack.roles
                ],
            }
        )
    return out
