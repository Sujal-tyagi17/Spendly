"""Request-level protections for the Spendly API.

* ``RateLimiter``: a sliding-window limiter kept **in this process's memory**. It is
  correct for the supported deployment (one uvicorn process). With several workers
  or instances each would count separately, so the effective limit multiplies; it
  is NOT a shared, distributed limiter.
* ``client_ip``: the peer address, or the first ``X-Forwarded-For`` entry only when
  ``SPENDLY_TRUST_PROXY=true`` (never trust that header from the open internet).
* ``AccessLogQueryFilter``: removes query strings from uvicorn access-log lines,
  because filters such as ``?merchants=…&search=…`` reveal private activity.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass

LOOPBACK = {"127.0.0.1", "::1", "localhost", "testclient"}  # "testclient" = Starlette's in-process test client


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


def is_loopback_host(host_header: str) -> bool:
    host = host_header.strip().lower()
    if host.startswith("["):  # [::1]:3000
        host = host[1:].split("]", 1)[0]
    elif host.count(":") == 1:
        host = host.split(":", 1)[0]
    return host in LOOPBACK


def client_ip(request) -> str:
    if env_flag("SPENDLY_TRUST_PROXY"):
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@dataclass(frozen=True)
class Limit:
    requests: int
    seconds: int


# Bucket → limit. Chosen so normal use never meets them (an import is 2–3 requests).
LIMITS: dict[str, Limit] = {
    "session": Limit(10, 60),          # new public sessions per client IP
    "session_global": Limit(60, 60),   # new public sessions in total (IP addresses can be spoofed)
    "import_preview": Limit(10, 60),   # PDF parsing is the most expensive operation
    "import_commit": Limit(20, 60),
    "report": Limit(20, 60),           # PDF report generation
    "export": Limit(30, 60),
    "write": Limit(120, 60),           # edits, bulk edits, budgets, reviews
    "destructive": Limit(10, 60),      # delete all data, demo reset, end session
    "ai": Limit(10, 60),
    "read": Limit(600, 60),            # everything else
}


def bucket_for(method: str, path: str) -> str:
    if path == "/api/session" and method == "POST":
        return "session"
    if path == "/api/import/preview":
        return "import_preview"
    if path.startswith("/api/import/") and path.endswith("/commit"):
        return "import_commit"
    if path.startswith("/api/report/"):
        return "report"
    if path == "/api/transactions/export.csv":
        return "export"
    if path.startswith("/api/ai/") or path.endswith("/ai"):
        return "ai"
    if path in {"/api/data", "/api/demo/reset", "/api/session"} and method in {"DELETE", "POST"}:
        return "destructive"
    if method in {"POST", "PATCH", "PUT", "DELETE"}:
        return "write"
    return "read"


class RateLimiter:
    def __init__(self, limits: dict[str, Limit] | None = None, clock=time.monotonic):
        self.limits = dict(limits or LIMITS)
        self._hits: dict[tuple[str, str], deque] = {}
        self._lock = threading.Lock()
        self._clock = clock

    def check(self, bucket: str, key: str) -> float | None:
        """Record a hit. Returns None if allowed, else seconds until the next slot frees up."""
        limit = self.limits[bucket]
        now = self._clock()
        with self._lock:
            hits = self._hits.setdefault((bucket, key), deque())
            while hits and now - hits[0] >= limit.seconds:
                hits.popleft()
            if len(hits) >= limit.requests:
                return max(0.0, limit.seconds - (now - hits[0]))
            hits.append(now)
            if len(self._hits) > 50_000:  # bound memory: drop idle keys
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] >= 3600]:
                    self._hits.pop(k, None)
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


class AccessLogQueryFilter(logging.Filter):
    """uvicorn.access records carry (client, method, path_with_query, http_version, status)."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str) and "?" in args[2]:
            record.args = (*args[:2], args[2].split("?", 1)[0] + "?[redacted]", *args[3:])
        return True


def install_access_log_filter() -> None:
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, AccessLogQueryFilter) for f in logger.filters):
        logger.addFilter(AccessLogQueryFilter())
