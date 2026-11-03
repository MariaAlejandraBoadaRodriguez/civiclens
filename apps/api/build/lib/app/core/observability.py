"""Request IDs, JSON logs and security headers (ROADMAP §5 "Logs & observability").

Every response carries ``X-Request-ID`` (the caller's, when it is a safe token, else a new one);
every log line is one JSON object with that ID and the negotiated locale. Logs never contain
query strings, request bodies or API keys: an access line is method, path, status, duration.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from contextvars import ContextVar

request_id: ContextVar[str] = ContextVar("request_id", default="-")
request_locale: ContextVar[str] = ContextVar("request_locale", default="-")
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
access_log = logging.getLogger("civiclens.access")

# Sent on every API answer. CSP is set per response where HTML is served (the report).
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
HSTS = "max-age=31536000; includeSubDomains"
REPORT_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'none'"


def new_request_id(incoming: str | None) -> str:
    return incoming if incoming and _SAFE_ID.match(incoming) else uuid.uuid4().hex


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id.get(),
            "locale": request_locale.get(),
        }
        for key in ("method", "path", "status", "ms"):
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers[:] = []
        logging.getLogger(name).propagate = name != "uvicorn.access"  # ours replaces it


def log_access(method: str, path: str, status: int, started: float) -> None:
    ms = round((time.perf_counter() - started) * 1000, 1)
    access_log.info(
        "%s %s %s",
        method,
        path,
        status,
        extra={"method": method, "path": path, "status": status, "ms": ms},
    )
