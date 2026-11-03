"""Who is calling, what they may do, and how often (US-24, ROADMAP 5e).

- **Anonymous** (the public demo, the web app): may read; may write only while
  ``ANONYMOUS_WRITES`` is on (the public demo); lower rate limit.
- **Agency key** (``X-API-Key``): scoped, revocable; an unknown or revoked key is refused (401)
  on every route, a key without the route's scope is refused (403).
- **Admin** (``Authorization: Bearer``): the web app's server, after GitHub OAuth of the single
  allowlisted admin, with a token the browser never sees. Only for ``/api/v1/keys``.

Errors are localized RFC 7807 problems. They are produced inside the CORS middleware, so the
browser can always read them (a response without CORS headers shows up as a "CORS error").
"""

from __future__ import annotations

import hmac
import math
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.api.problems import ProblemError, problem_body
from app.config import settings
from app.core import keys
from app.i18n.loader import Translator


@dataclass(frozen=True)
class Principal:
    kind: str  # "anonymous" | "key" | "admin"
    key_id: uuid.UUID | None = None
    scopes: frozenset[str] = field(default_factory=frozenset)
    name: str = "anonymous"


ANONYMOUS = Principal("anonymous")

# Routes that start heavy background work get their own, stricter limit.
HEAVY = (
    ("POST", "/api/v1/datasets"),
    ("POST", "/api/v1/datasets/", "/recipes/apply"),
    ("POST", "/api/v1/models/", "/run"),
)


def is_heavy(method: str, path: str) -> bool:
    for rule in HEAVY:
        if method != rule[0]:
            continue
        if len(rule) == 2 and path.rstrip("/") == rule[1]:
            return True
        if len(rule) == 3 and path.startswith(rule[1]) and path.endswith(rule[2]):
            return True
    return False


class RateLimiter:
    """Fixed one-minute windows per (caller, class). In memory: one API instance (ROADMAP §2)."""

    def __init__(self) -> None:
        self._windows: dict[tuple[str, str], tuple[int, int]] = {}

    def hit(self, bucket: str, kind: str, limit: int, now: float | None = None) -> int | None:
        """Count one request; return the seconds to wait when over ``limit``, else ``None``."""
        now = time.time() if now is None else now
        window = int(now // 60)
        start, count = self._windows.get((bucket, kind), (window, 0))
        if start != window:
            start, count = window, 0
        if count >= limit:
            return max(1, math.ceil((start + 1) * 60 - now))
        self._windows[(bucket, kind)] = (start, count + 1)
        if len(self._windows) > 50_000:  # forget finished windows
            self._windows = {k: v for k, v in self._windows.items() if v[0] == window}
        return None

    def reset(self) -> None:
        self._windows.clear()


limiter = RateLimiter()

# fingerprint(key) → key id, so argon2 runs once per key per process, not once per request.
_verified: dict[str, uuid.UUID] = {}
_last_used_written: dict[uuid.UUID, float] = {}


def problem(
    request: Request, status: int, code: str, headers: dict[str, str] | None = None, **params: Any
) -> JSONResponse:
    t: Translator = getattr(request.state, "t", Translator("en"))
    return JSONResponse(
        problem_body(t, status, code, params, request.url.path),
        status_code=status,
        media_type="application/problem+json",
        headers={"Content-Language": t.lang, **(headers or {})},
    )


def _resolve_key(raw: str) -> Principal | None:
    """The principal for a presented key, or ``None`` when it is unknown, wrong or revoked."""
    from app.db.models import ApiKey
    from app.db.session import SessionLocal

    prefix = keys.prefix_of(raw)
    if prefix is None:
        return None
    with SessionLocal() as session:
        row = session.query(ApiKey).filter(ApiKey.prefix == prefix).one_or_none()
        if row is None or row.revoked_at is not None:
            return None
        fp = keys.fingerprint(raw)
        if _verified.get(fp) != row.id:
            if not keys.verify(raw, row.hash):
                return None
            _verified[fp] = row.id
        now = time.time()
        if now - _last_used_written.get(row.id, 0) > 60:  # at most one write a minute per key
            row.last_used_at = datetime.now(UTC)
            session.commit()
            _last_used_written[row.id] = now
        return Principal("key", row.id, frozenset(row.scopes or []), row.name)


def client_ip(request: Request) -> str:
    """The caller's address for rate limiting. Behind ``TRUSTED_PROXY_HOPS`` proxies, the entry
    they appended to ``X-Forwarded-For``; anything left of it can be forged by the caller."""
    hops = settings.trusted_proxy_hops
    if hops > 0:
        chain = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",")]
        chain = [p for p in chain if p]
        if len(chain) >= hops:
            return chain[-hops]
    return request.client.host if request.client else "unknown"


def forget_key(key_id: uuid.UUID) -> None:
    """Drop cached verifications of a revoked key (revocation is checked on every request
    anyway; this only frees memory)."""
    for fp in [fp for fp, kid in _verified.items() if kid == key_id]:
        _verified.pop(fp, None)


async def security_middleware(request: Request, call_next):
    """Identify the caller (401 for a bad key) and apply the rate limit (429)."""
    principal = ANONYMOUS
    raw = request.headers.get("x-api-key")
    if raw:
        resolved = await run_in_threadpool(_resolve_key, raw.strip())  # argon2 + DB: off the loop
        if resolved is None:
            return problem(request, 401, "auth.invalid_key")
        principal = resolved
    request.state.principal = principal

    if request.url.path.startswith("/api/") and request.method != "OPTIONS":
        heavy = is_heavy(request.method, request.url.path)
        if principal.kind == "key":
            bucket = f"key:{principal.key_id}"
            limit = settings.rate_limit_heavy_key if heavy else settings.rate_limit_key
        else:
            bucket = f"ip:{client_ip(request)}"
            limit = settings.rate_limit_heavy_anonymous if heavy else settings.rate_limit_anonymous
        wait = limiter.hit(bucket, "heavy" if heavy else "default", limit)
        if wait is not None:
            return problem(
                request, 429, "rate_limit.exceeded", {"Retry-After": str(wait)}, retry_after=wait
            )
    return await call_next(request)


def current_principal(request: Request) -> Principal:
    return getattr(request.state, "principal", ANONYMOUS)


def require_scope(scope: str):
    """Dependency for write routes: a key needs ``scope``; anonymous callers are let through
    only while ``ANONYMOUS_WRITES`` is on (the public demo)."""

    def check(request: Request) -> Principal:
        principal = current_principal(request)
        if principal.kind == "key":
            if scope not in principal.scopes:
                raise ProblemError(403, "auth.insufficient_scope", scope=scope)
            return principal
        if not settings.anonymous_writes:
            raise ProblemError(401, "auth.missing_key", scope=scope)
        return principal

    return check


def require_admin(request: Request) -> str:
    """Dependency for ``/api/v1/keys``: the admin token from the web app's server. Returns the
    admin's GitHub login (for the audit log)."""
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not token:
        if current_principal(request).kind == "key":
            raise ProblemError(403, "auth.admin_only")
        raise ProblemError(401, "auth.admin_required")
    expected = settings.admin_api_token
    if not expected or not hmac.compare_digest(token.encode(), expected.encode()):
        raise ProblemError(401, "auth.admin_required")
    return (request.headers.get("x-admin-login") or "admin")[:120]
