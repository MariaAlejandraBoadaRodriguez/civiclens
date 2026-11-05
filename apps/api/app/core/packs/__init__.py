"""Domain packs: declarative layers on top of the generic analysis.

Each pack is one YAML file in ``definitions/`` (roles, goals, KPIs, SQL questions, ML objectives,
dashboard layout); its texts live in the ``packs`` i18n catalog. A new pack is a new file plus
its EN/ES texts: the engine does not change. Packs never replace the generic analysis: a role
that is not mapped simply drops the pack items that need it, and the generic items stay.

Roles are matched on header names (exact, token or partial match against EN/ES/FR synonyms) and
on column kinds, with a confidence the user sees and can override.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from app.core.analysis.questions import positive_expr, q
from app.core.analysis.table import ColumnMeta

DEFINITIONS = Path(__file__).resolve().parent / "definitions"
TEMPLATE = re.compile(r"\{(positive:)?([a-z_|]+)\}")


@dataclass(frozen=True)
class Role:
    id: str
    kinds: tuple[str, ...]
    synonyms: tuple[str, ...] = ()
    key: bool = False
    target: bool = False
    sensitive: bool = False
    canonical: str | None = None

    def accepts(self, meta: ColumnMeta) -> bool:
        if "binary" in self.kinds and meta.binary and meta.distinct == 2:
            return True
        return meta.kind in self.kinds


@dataclass(frozen=True)
class Pack:
    id: str
    order: int
    engine: str
    detect: dict[str, Any]
    roles: tuple[Role, ...]
    goals: tuple[dict[str, Any], ...]
    kpis: tuple[dict[str, Any], ...]
    questions: tuple[dict[str, Any], ...]
    ml: tuple[dict[str, Any], ...]
    layout: dict[str, Any] = field(default_factory=dict)
    # {limit} in SQL: per-category thresholds (e.g. pollutant → µg/m3) and a fallback value.
    limits: dict[str, float] = field(default_factory=dict)
    default_limit: float | None = None

    @property
    def default_goal(self) -> str:
        return next((g["id"] for g in self.goals if g.get("default")), self.goals[0]["id"])

    def role(self, role_id: str) -> Role | None:
        return next((r for r in self.roles if r.id == role_id), None)


@cache
def packs() -> dict[str, Pack]:
    out = {}
    for path in sorted(DEFINITIONS.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        roles = tuple(
            Role(
                id=r["id"],
                kinds=tuple(r.get("kinds", [])),
                synonyms=tuple(r.get("synonyms", [])),
                key=bool(r.get("key")),
                target=bool(r.get("target")),
                sensitive=bool(r.get("sensitive")),
                canonical=r.get("canonical"),
            )
            for r in raw.get("roles", [])
        )
        out[raw["id"]] = Pack(
            id=raw["id"],
            order=int(raw.get("order", 50)),
            engine=raw.get("engine", "generic"),
            detect=raw.get("detect", {}),
            roles=roles,
            goals=tuple(raw.get("goals", [{"id": "explore", "default": True}])),
            kpis=tuple(raw.get("kpis", [])),
            questions=tuple(raw.get("questions", [])),
            ml=tuple(raw.get("ml", [])),
            layout=raw.get("layout", {}),
            limits={str(k).upper(): float(v) for k, v in (raw.get("limits") or {}).items()},
            default_limit=raw.get("default_limit"),
        )
    return dict(sorted(out.items(), key=lambda kv: kv[1].order))


# --------------------------------------------------------------------------- role matching


def _tokens(name: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", name.lower()) if t}


def match_confidence(role: Role, meta: ColumnMeta) -> float:
    """0 (no match) … 0.95 (exact name) for one column against one role."""
    if not role.accepts(meta):
        return 0.0
    name = meta.name.lower()
    tokens = _tokens(name)
    best = 0.0
    for syn in role.synonyms:
        syn = syn.lower()
        if name == syn:
            best = max(best, 0.95)
        elif _tokens(syn) <= tokens and "_" in syn:
            best = max(best, 0.85)
        elif syn in tokens:
            best = max(best, 0.75)
        elif len(syn) >= 4 and syn in name:
            best = max(best, 0.55)
    return best


def suggest_roles(
    pack: Pack, metas: list[ColumnMeta], canonical: dict[str, str] | None = None
) -> dict[str, dict[str, Any]]:
    """Best column per role (each column used once), with its confidence. ``canonical`` maps a
    canonical procurement field to the ``data`` column it was mapped to at ingest."""
    canonical = canonical or {}
    candidates: list[tuple[float, int, str, str]] = []
    for i, role in enumerate(pack.roles):
        if role.canonical and role.canonical in canonical:
            candidates.append((0.9, -i, role.id, canonical[role.canonical]))
            continue
        for meta in metas:
            conf = match_confidence(role, meta)
            if conf > 0:
                # Key roles win ties: they decide whether the pack applies at all.
                candidates.append((conf + (0.01 if role.key else 0), -i, role.id, meta.name))
    out: dict[str, dict[str, Any]] = {}
    used: set[str] = set()
    by_name = {m.name: m for m in metas}
    for conf, _, role_id, column in sorted(candidates, reverse=True):
        if role_id in out or column in used:
            continue
        out[role_id] = {"column": column, "confidence": round(min(conf, 0.95), 2)}
        role = pack.role(role_id)
        if role and role.target and column in by_name:
            out[role_id]["positive"] = guess_positive(by_name[column])
        used.add(column)
    return out


POSITIVE_WORDS = {"yes", "si", "sí", "oui", "true", "1", "bad", "default", "y", "s"}


def guess_positive(meta: ColumnMeta) -> str | None:
    """The value of a binary target that means "it happened" (default, converted …): a value
    spelled like yes / true / bad, else the minority value (events are usually the rarer case,
    e.g. 300 bad loans out of 1,000 in the German credit data, coded 0)."""
    values = [t for t in meta.top if t["value"] not in ("", None)]
    if len(values) < 2:
        return None
    words = [t for t in values if str(t["value"]).strip().lower() in POSITIVE_WORDS - {"1", "true"}]
    if words:
        return str(words[0]["value"])
    return str(min(values, key=lambda t: t["count"])["value"])


def score(
    pack: Pack, metas: list[ColumnMeta], canonical_fields: set[str], mapping: dict[str, Any]
) -> float:
    """How well the file fits the pack, 0–1 (General is the floor)."""
    detect = pack.detect
    if "base_score" in detect:
        return float(detect["base_score"])
    if pack.engine == "procurement_star":
        ok = set(detect.get("canonical_all", [])) <= canonical_fields
        ok = ok and bool(set(detect.get("canonical_any_supplier", [])) & canonical_fields)
        ok = ok and bool(set(detect.get("canonical_any_context", [])) & canonical_fields)
        return float(detect.get("score", 0.9)) if ok else 0.0
    if not any(r in mapping for r in detect.get("require_any", [])):
        return 0.0
    needs_one_of = detect.get("require_all_any", [])
    if needs_one_of and not any(r in mapping for r in needs_one_of):
        return 0.0
    weights = {r.id: (2.0 if r.key or r.target else 1.0) for r in pack.roles if not r.sensitive}
    got = sum(weights[r] * mapping[r]["confidence"] for r in weights if r in mapping)
    total = sum(weights.values()) or 1.0
    value = min(1.0, 0.25 + got / total)
    return round(value, 2) if value >= float(detect.get("min_score", 0.35)) else 0.0


def suggestions(
    metas: list[ColumnMeta], canonical: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    """Every pack with its fit score and suggested role mapping, best first."""
    canonical = canonical or {}
    out = []
    for pack in packs().values():
        mapping = suggest_roles(pack, metas, canonical)
        out.append(
            {
                "pack": pack.id,
                "score": score(pack, metas, set(canonical), mapping),
                "roles": mapping,
            }
        )
    out.sort(key=lambda s: (-s["score"], packs()[s["pack"]].order))
    return out


# --------------------------------------------------------------------------- templates


class MissingRole(KeyError):
    pass


def limit_expr(
    pack: Pack | None, roles: dict[str, dict[str, Any]], metas: dict[str, ColumnMeta]
) -> str:
    """``{limit}``: the mapped limit column, else the pack's limit for the row's category
    (pollutant), else its default limit."""
    from app.core.analysis.questions import lit

    entry = roles.get("limit") or {}
    if entry.get("column") in metas:
        return q(entry["column"])
    if pack is None or pack.default_limit is None and not pack.limits:
        raise MissingRole("limit")
    default = "NULL" if pack.default_limit is None else repr(float(pack.default_limit))
    category = (roles.get("pollutant") or {}).get("column")
    if not pack.limits or category not in metas:
        return default
    cases = " ".join(f"WHEN {lit(k)} THEN {v!r}" for k, v in pack.limits.items())
    return f"(CASE UPPER(CAST({q(category)} AS VARCHAR)) {cases} ELSE {default} END)"


def render(
    sql: str,
    roles: dict[str, dict[str, Any]],
    metas: dict[str, ColumnMeta],
    pack: Pack | None = None,
) -> str:
    """Fill ``{role}`` (quoted column), ``{a|b}`` (first mapped of a, b), ``{positive:role}``
    (TRUE for the flag's positive value) and ``{limit}`` (see ``limit_expr``). Raises
    MissingRole when a role is not mapped."""

    def column(spec: str) -> ColumnMeta:
        for role_id in spec.split("|"):
            entry = roles.get(role_id)
            if entry and entry.get("column") in metas:
                return metas[entry["column"]]
        raise MissingRole(spec)

    def sub(match: re.Match[str]) -> str:
        positive, spec = match.group(1), match.group(2)
        if spec == "limit" and not positive:
            return limit_expr(pack, roles, metas)
        meta = column(spec)
        if positive:
            role_id = spec.split("|")[0]
            return positive_expr(meta, (roles.get(role_id) or {}).get("positive"))
        return q(meta.name)

    return TEMPLATE.sub(sub, sql)


def requires_ok(
    item: dict[str, Any], roles: dict[str, dict[str, Any]], metas: dict[str, ColumnMeta]
) -> bool:
    mapped = {r for r, e in roles.items() if e.get("column") in metas}
    if not set(item.get("requires", [])) <= mapped:
        return False
    any_of = item.get("requires_any")
    return not any_of or bool(set(any_of) & mapped)
