"""Database connections, data modes, visitor sessions and pending import previews.

Local use (default)
    One SQLite file per data mode (``data/spendly_demo.db`` / ``data/spendly_user.db``),
    exactly like the Streamlit app.

Public deployment (``SPENDLY_PUBLIC_DEPLOYMENT=true``)
    The server issues each visitor a random session token (``POST /api/session``,
    256 bits from ``secrets``) which the browser sends as ``X-Spendly-Session``.
    Only tokens issued by this process are accepted; unknown, expired or ended
    tokens get 401. Each session's demo and user databases are private,
    in-memory, and expire after inactivity, so nothing is written to disk.
    A session token is a bearer secret, not an identity: there are no accounts.

All of this state lives in one process's memory, so public mode requires a single
uvicorn worker and a single instance (see README "Security").

SQLite connections are shared between FastAPI worker threads, so every request
holds the connection's lock while it uses it.
"""

from __future__ import annotations

import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

from src import config, database, pipeline
from src.pipeline import ImportPreview

MODES = ("demo", "user")
SESSION_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
SESSION_TTL_SECONDS = 2 * 60 * 60
MAX_SESSIONS = 200
PREVIEW_TTL_SECONDS = 30 * 60
MAX_PREVIEWS = 100
MAX_PREVIEWS_PER_OWNER = 3
# When full, only sessions idle this long may be dropped to make room; active visitors
# are never evicted (that would let anyone wipe other people's sessions by opening new ones).
EVICTABLE_IDLE_SECONDS = 15 * 60


class SessionError(ValueError):
    pass


class CapacityError(RuntimeError):
    """No room for another public session right now."""


@dataclass
class _Db:
    conn: sqlite3.Connection
    lock: threading.Lock = field(default_factory=threading.Lock)
    last_used: float = field(default_factory=time.time)


def _prepare(conn: sqlite3.Connection, mode: str) -> sqlite3.Connection:
    if mode == "demo" and database.count_transactions(conn) == 0:
        pipeline.load_demo_dataset(conn)
    return conn


class ConnectionManager:
    def __init__(self, public: bool):
        self.public = public
        self._files: dict[str, _Db] = {}
        self._sessions: dict[tuple[str, str], _Db] = {}
        self._issued: dict[str, float] = {}  # token -> last used (public mode)
        self._guard = threading.Lock()

    # ---------------------------------------------------------- sessions
    def issue(self) -> str | None:
        """New server-generated session token (public mode only)."""
        if not self.public:
            return None
        token = secrets.token_urlsafe(32)
        with self._guard:
            self._evict_locked()
            if len(self._issued) >= MAX_SESSIONS:
                now = time.time()
                idle = [t for t, used in self._issued.items() if now - used >= EVICTABLE_IDLE_SECONDS]
                if not idle:
                    raise CapacityError("Spendly is busy right now. Please try again in a few minutes.")
                self._drop_locked(min(idle, key=self._issued.get))
            self._issued[token] = time.time()
        return token

    def revoke(self, session: str | None) -> bool:
        if not self.public or not session:
            return False
        with self._guard:
            if session not in self._issued:
                return False
            self._drop_locked(session)
            return True

    def _drop_locked(self, token: str) -> None:
        self._issued.pop(token, None)
        for mode in MODES:
            db = self._sessions.pop((token, mode), None)
            if db is not None:
                with db.lock:
                    db.conn.close()

    def _key(self, session: str | None) -> str:
        if not self.public:
            return "local"
        if not session or not SESSION_PATTERN.match(session):
            raise SessionError("A session is required. Start one with POST /api/session.")
        with self._guard:
            self._evict_locked()
            if session not in self._issued:
                raise SessionError("This session has expired or was ended. Start a new one.")
            self._issued[session] = time.time()
        return session

    def _get(self, mode: str, session: str | None) -> _Db:
        if mode not in MODES:
            raise SessionError("Unknown data mode.")
        key = self._key(session)
        with self._guard:
            if not self.public:
                db = self._files.get(mode)
                if db is None:
                    db = _Db(_prepare(database.connect_mode(mode), mode))
                    self._files[mode] = db
                return db
            db = self._sessions.get((key, mode))
            if db is None:
                db = _Db(_prepare(database.connect(":memory:"), mode))
                self._sessions[(key, mode)] = db
            db.last_used = time.time()
            return db

    def _evict_locked(self) -> None:
        now = time.time()
        for token in [t for t, used in self._issued.items() if now - used > SESSION_TTL_SECONDS]:
            self._drop_locked(token)

    @contextmanager
    def connection(self, mode: str, session: str | None) -> Iterator[sqlite3.Connection]:
        db = self._get(mode, session)
        with db.lock:
            yield db.conn

    def owner(self, session: str | None) -> str:
        return self._key(session)

    def session_count(self) -> int:
        return len(self._issued)

    def close_all(self) -> None:
        with self._guard:
            for db in [*self._files.values(), *self._sessions.values()]:
                db.conn.close()
            self._files.clear()
            self._sessions.clear()
            self._issued.clear()


@dataclass
class _Pending:
    owner: str
    mode: str
    preview: ImportPreview
    created: float = field(default_factory=time.time)


class PreviewStore:
    """Holds parsed-but-not-imported previews. The PDF bytes are never kept —
    only the extracted (already masked) rows, until the user confirms or the
    preview expires."""

    def __init__(self):
        self._items: dict[str, _Pending] = {}
        self._lock = threading.Lock()

    def put(self, owner: str, mode: str, preview: ImportPreview) -> str:
        token = secrets.token_urlsafe(18)
        with self._lock:
            self._expire_locked()
            mine = sorted((t for t, i in self._items.items() if i.owner == owner), key=lambda t: self._items[t].created)
            for old in mine[: max(0, len(mine) - MAX_PREVIEWS_PER_OWNER + 1)]:  # one visitor can't crowd out others
                self._items.pop(old)
            self._items[token] = _Pending(owner, mode, preview)
        return token

    def get(self, token: str, owner: str, mode: str) -> ImportPreview | None:
        with self._lock:
            self._expire_locked()
            item = self._items.get(token)
            if item is None or item.owner != owner or item.mode != mode:
                return None
            return item.preview

    def pop(self, token: str, owner: str, mode: str) -> ImportPreview | None:
        with self._lock:
            item = self._items.get(token)
            if item is None or item.owner != owner or item.mode != mode:
                return None
            return self._items.pop(token).preview

    def discard_owner(self, owner: str) -> None:
        with self._lock:
            for token in [t for t, i in self._items.items() if i.owner == owner]:
                self._items.pop(token)

    def _expire_locked(self) -> None:
        now = time.time()
        for token in [t for t, i in self._items.items() if now - i.created > PREVIEW_TTL_SECONDS]:
            self._items.pop(token)
        while len(self._items) > MAX_PREVIEWS:
            oldest = min(self._items, key=lambda t: self._items[t].created)
            self._items.pop(oldest)


def is_public() -> bool:
    return config._env_bool("SPENDLY_PUBLIC_DEPLOYMENT", config.PUBLIC_DEPLOYMENT)
