"""Agency API keys: format, argon2 hashing and verification (US-24, ADR-0003).

A key looks like ``cl_live_ab12cd34.<43 url-safe chars>``. The part before the dot is a public,
non-secret prefix stored in clear for lookup; only the argon2id hash of the whole key is stored.
The full key is shown once, when it is created.
"""

from __future__ import annotations

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

SCOPES = ("datasets:write", "recipes:write", "models:run", "reports:read")
PREFIX_START = "cl_live_"

# Moderate cost: keys are long random secrets (no brute force risk like passwords), and a
# verification happens at most once per key per process thanks to the cache in app.api.security.
_hasher = PasswordHasher(time_cost=2, memory_cost=19_456, parallelism=1)


def generate() -> tuple[str, str]:
    """Return ``(full_key, prefix)``."""
    prefix = PREFIX_START + secrets.token_hex(4)
    return f"{prefix}.{secrets.token_urlsafe(32)}", prefix


def hash_key(key: str) -> str:
    return _hasher.hash(key)


def verify(key: str, stored_hash: str) -> bool:
    try:
        return _hasher.verify(stored_hash, key)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def prefix_of(key: str) -> str | None:
    """The lookup prefix of a well-formed key, else ``None``."""
    prefix, dot, secret = key.partition(".")
    if not dot or not secret or not prefix.startswith(PREFIX_START) or len(prefix) != 16:
        return None
    return prefix


def fingerprint(key: str) -> str:
    """Non-reversible cache key for a verified key (never logged, never stored)."""
    return hashlib.sha256(key.encode()).hexdigest()
