"""Database connections, data modes, visitor sessions and pending import previews.

Local use (default)
    One SQLite file per data mode (``data/spendly_demo.db`` / ``data/spendly_user.db``),
    exactly like the Streamlit app.

Public deployment (``SPENDLY_PUBLIC_DEPLOYMENT=true``)
    Each visitor sends a random session id (``X-Spendly-Session``). Their demo and
    user databases are private, in-memory, and expire after inactivity, so no
    visitor can see another visitor's data and nothing is written to disk.

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


class SessionError(ValueError):
    pass


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
        self._guard = threading.Lock()

    def _key(self, session: str | None) -> str:
        if not self.public:
            return "local"
        if not session or not SESSION_PATTERN.match(session):
            raise SessionError("A valid X-Spendly-Session header is required on this deployment.")
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
            self._evict_locked()
            db = self._sessions.get((key, mode))
            if db is None:
                db = _Db(_prepare(database.connect(":memory:"), mode))
                self._sessions[(key, mode)] = db
            db.last_used = time.time()
            return db

    def _evict_locked(self) -> None:
        now = time.time()
        for k in [k for k, db in self._sessions.items() if now - db.last_used > SESSION_TTL_SECONDS]:
            self._sessions.pop(k).conn.close()
        while len(self._sessions) >= MAX_SESSIONS * 2:
            oldest = min(self._sessions, key=lambda k: self._sessions[k].last_used)
            self._sessions.pop(oldest).conn.close()

    @contextmanager
    def connection(self, mode: str, session: str | None) -> Iterator[sqlite3.Connection]:
        db = self._get(mode, session)
        with db.lock:
            yield db.conn

    def owner(self, session: str | None) -> str:
        return self._key(session)

    def close_all(self) -> None:
        with self._guard:
            for db in [*self._files.values(), *self._sessions.values()]:
                db.conn.close()
            self._files.clear()
            self._sessions.clear()


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
