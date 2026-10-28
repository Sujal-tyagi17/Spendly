"""SQLite data-access layer.

* Schema is created automatically (``init_db``).
* Every query uses ``?`` / ``:name`` parameters — values are never formatted
  into SQL strings.
* Multi-step writes run inside a single transaction (``with conn:``) so an
  import either fully succeeds or leaves the database untouched.

Note: the SQLite file is a normal, **unencrypted** file on disk. See the
README "Privacy" section for where it lives and how to delete it.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from src import config
from src.privacy import get_logger

log = get_logger(__name__)

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS categories (
    id            INTEGER PRIMARY KEY,
    category_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS statements (
    id                      INTEGER PRIMARY KEY,
    display_name            TEXT NOT NULL,
    file_hash               TEXT UNIQUE,          -- sha256 of the file, used to block re-imports
    parser_name             TEXT NOT NULL,
    statement_period_start  TEXT,
    statement_period_end    TEXT,
    processing_status       TEXT NOT NULL DEFAULT 'imported',
    rows_extracted          INTEGER NOT NULL DEFAULT 0,
    rows_imported           INTEGER NOT NULL DEFAULT 0,
    rows_invalid            INTEGER NOT NULL DEFAULT 0,
    rows_skipped_duplicates INTEGER NOT NULL DEFAULT 0,
    balance_checked_pairs   INTEGER NOT NULL DEFAULT 0,
    balance_mismatches      INTEGER NOT NULL DEFAULT 0,
    warnings                TEXT NOT NULL DEFAULT '[]',   -- JSON list
    created_at              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id                    INTEGER PRIMARY KEY,
    transaction_date      TEXT NOT NULL,                 -- ISO YYYY-MM-DD
    description           TEXT NOT NULL,                 -- original wording, identifiers masked
    normalized_merchant   TEXT NOT NULL,
    amount_paise          INTEGER NOT NULL CHECK (amount_paise > 0),
    direction             TEXT NOT NULL CHECK (direction IN ('debit', 'credit')),
    transaction_type      TEXT NOT NULL CHECK (transaction_type IN
                              ('expense', 'income', 'refund', 'transfer', 'cc_repayment', 'other')),
    category              TEXT NOT NULL REFERENCES categories(category_name),
    categorization_method TEXT NOT NULL,                 -- rule | merchant | ai | manual | none
    review_status         TEXT NOT NULL DEFAULT 'ok',    -- ok | needs_review | reviewed
    review_reason         TEXT,
    is_transfer           INTEGER NOT NULL DEFAULT 0,
    is_possible_duplicate INTEGER NOT NULL DEFAULT 0,
    balance_paise         INTEGER,
    fingerprint           TEXT NOT NULL,
    source_statement_id   INTEGER NOT NULL REFERENCES statements(id) ON DELETE CASCADE,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_txn_date       ON transactions(transaction_date);
CREATE INDEX IF NOT EXISTS idx_txn_category   ON transactions(category);
CREATE INDEX IF NOT EXISTS idx_txn_merchant   ON transactions(normalized_merchant);
CREATE INDEX IF NOT EXISTS idx_txn_statement  ON transactions(source_statement_id);
CREATE INDEX IF NOT EXISTS idx_txn_fp         ON transactions(fingerprint);
CREATE INDEX IF NOT EXISTS idx_txn_type_date  ON transactions(transaction_type, transaction_date);

-- Rows that could not be imported, with the reason (no raw values stored).
CREATE TABLE IF NOT EXISTS import_issues (
    id           INTEGER PRIMARY KEY,
    statement_id INTEGER NOT NULL REFERENCES statements(id) ON DELETE CASCADE,
    row_number   INTEGER,
    page         INTEGER,
    reason       TEXT NOT NULL
);

-- User decisions on recurring-payment candidates (keyed by merchant).
CREATE TABLE IF NOT EXISTS recurring_decisions (
    merchant   TEXT PRIMARY KEY,
    decision   TEXT NOT NULL CHECK (decision IN ('confirmed', 'rejected')),
    decided_at TEXT NOT NULL
);

-- User decisions on anomaly alerts, so dismissed alerts don't come back.
CREATE TABLE IF NOT EXISTS anomaly_reviews (
    transaction_id INTEGER PRIMARY KEY REFERENCES transactions(id) ON DELETE CASCADE,
    status         TEXT NOT NULL CHECK (status IN ('dismissed', 'expected')),
    reviewed_at    TEXT NOT NULL
);

-- Log of manual category corrections (for the Data Quality page).
CREATE TABLE IF NOT EXISTS manual_corrections (
    id             INTEGER PRIMARY KEY,
    transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    field          TEXT NOT NULL,
    old_value      TEXT,
    new_value      TEXT,
    corrected_at   TEXT NOT NULL
);
"""


class DatabaseError(RuntimeError):
    """Raised with a user-friendly message when the database fails."""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(path: str | Path) -> sqlite3.Connection:
    try:
        # isolation_level=None -> we control transactions explicitly with BEGIN/COMMIT.
        conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        init_db(conn)
        return conn
    except sqlite3.Error as exc:
        log.error("Database initialisation failed: %s", type(exc).__name__)
        raise DatabaseError(
            "Could not open the local database. Check that the data folder is writable, "
            "or delete the .db file to start fresh."
        ) from exc


def connect_mode(mode: str) -> sqlite3.Connection:
    return connect(config.db_path(mode))


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    with transaction(conn):
        conn.executemany(
            "INSERT OR IGNORE INTO categories (category_name) VALUES (?)",
            [(c,) for c in config.CATEGORIES],
        )


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Commit on success, roll back everything on any error."""
    try:
        conn.execute("BEGIN")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


# ---------------------------------------------------------------- statements

def statement_exists(conn: sqlite3.Connection, file_hash: str) -> bool:
    row = conn.execute("SELECT 1 FROM statements WHERE file_hash = ?", (file_hash,)).fetchone()
    return row is not None


def insert_statement(conn: sqlite3.Connection, *, display_name: str, file_hash: str | None,
                     parser_name: str, period_start: str | None, period_end: str | None,
                     rows_extracted: int, rows_imported: int, rows_invalid: int,
                     rows_skipped_duplicates: int, balance_checked_pairs: int,
                     balance_mismatches: int, warnings: list[str]) -> int:
    cur = conn.execute(
        """INSERT INTO statements (display_name, file_hash, parser_name, statement_period_start,
               statement_period_end, processing_status, rows_extracted, rows_imported, rows_invalid,
               rows_skipped_duplicates, balance_checked_pairs, balance_mismatches, warnings, created_at)
           VALUES (?, ?, ?, ?, ?, 'imported', ?, ?, ?, ?, ?, ?, ?, ?)""",
        (display_name, file_hash, parser_name, period_start, period_end, rows_extracted,
         rows_imported, rows_invalid, rows_skipped_duplicates, balance_checked_pairs,
         balance_mismatches, json.dumps(warnings), now_iso()),
    )
    return int(cur.lastrowid)


def list_statements(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM statements ORDER BY created_at, id").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["warnings"] = json.loads(item.get("warnings") or "[]")
        result.append(item)
    return result


def coverage_period(conn: sqlite3.Connection) -> tuple[str | None, str | None]:
    """Overall date range covered by imported statements."""
    row = conn.execute(
        """SELECT MIN(COALESCE(s.statement_period_start, t.min_date)),
                  MAX(COALESCE(s.statement_period_end, t.max_date))
           FROM statements s
           JOIN (SELECT source_statement_id, MIN(transaction_date) AS min_date,
                        MAX(transaction_date) AS max_date
                 FROM transactions GROUP BY source_statement_id) t
             ON t.source_statement_id = s.id"""
    ).fetchone()
    return (row[0], row[1]) if row else (None, None)


# -------------------------------------------------------------- transactions

TRANSACTION_COLUMNS = (
    "transaction_date", "description", "normalized_merchant", "amount_paise", "direction",
    "transaction_type", "category", "categorization_method", "review_status", "review_reason",
    "is_transfer", "is_possible_duplicate", "balance_paise", "fingerprint", "source_statement_id",
)


def insert_transactions(conn: sqlite3.Connection, rows: list[dict]) -> int:
    stamp = now_iso()
    placeholders = ", ".join("?" for _ in TRANSACTION_COLUMNS)
    sql = (f"INSERT INTO transactions ({', '.join(TRANSACTION_COLUMNS)}, created_at, updated_at) "
           f"VALUES ({placeholders}, ?, ?)")
    conn.executemany(sql, [tuple(row[c] for c in TRANSACTION_COLUMNS) + (stamp, stamp) for row in rows])
    return len(rows)


def insert_import_issues(conn: sqlite3.Connection, statement_id: int, issues: list[dict]) -> None:
    conn.executemany(
        "INSERT INTO import_issues (statement_id, row_number, page, reason) VALUES (?, ?, ?, ?)",
        [(statement_id, i.get("row_number"), i.get("page"), i["reason"]) for i in issues],
    )


def count_transactions(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0])


def get_transaction(conn: sqlite3.Connection, transaction_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
    return dict(row) if row else None


def update_transaction_fields(conn: sqlite3.Connection, transaction_id: int, changes: dict) -> None:
    """Apply a manual correction and log it. Only whitelisted columns."""
    allowed = {"category", "transaction_type", "review_status", "is_possible_duplicate"}
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError(f"Not editable: {sorted(unknown)}")
    current = get_transaction(conn, transaction_id)
    if current is None:
        raise ValueError(f"Transaction {transaction_id} not found")

    stamp = now_iso()
    with transaction(conn):
        for column, value in changes.items():
            if current[column] == value:
                continue
            # Column names come from the whitelist above, never from user input.
            conn.execute(f"UPDATE transactions SET {column} = ?, updated_at = ? WHERE id = ?",
                         (value, stamp, transaction_id))
            conn.execute(
                """INSERT INTO manual_corrections (transaction_id, field, old_value, new_value, corrected_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (transaction_id, column, str(current[column]), str(value), stamp),
            )
        if "category" in changes or "transaction_type" in changes:
            new_type = changes.get("transaction_type", current["transaction_type"])
            conn.execute(
                """UPDATE transactions SET categorization_method = 'manual', review_status = 'reviewed',
                       review_reason = NULL, is_transfer = ? WHERE id = ?""",
                (1 if new_type == "transfer" else 0, transaction_id),
            )


def delete_transaction(conn: sqlite3.Connection, transaction_id: int) -> None:
    with transaction(conn):
        conn.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))


def clear_all_data(conn: sqlite3.Connection) -> None:
    """Delete every imported statement, transaction and decision."""
    with transaction(conn):
        for table in ("anomaly_reviews", "manual_corrections", "import_issues",
                      "transactions", "statements", "recurring_decisions"):
            conn.execute(f"DELETE FROM {table}")  # fixed table names, not user input
    conn.execute("VACUUM")  # actually shrink the file so deleted rows don't linger


# ------------------------------------------------------------ user decisions

def set_recurring_decision(conn: sqlite3.Connection, merchant: str, decision: str | None) -> None:
    with transaction(conn):
        if decision is None:
            conn.execute("DELETE FROM recurring_decisions WHERE merchant = ?", (merchant,))
        else:
            conn.execute(
                """INSERT INTO recurring_decisions (merchant, decision, decided_at) VALUES (?, ?, ?)
                   ON CONFLICT(merchant) DO UPDATE SET decision = excluded.decision,
                                                       decided_at = excluded.decided_at""",
                (merchant, decision, now_iso()),
            )


def recurring_decisions(conn: sqlite3.Connection) -> dict[str, str]:
    return {r["merchant"]: r["decision"] for r in conn.execute("SELECT * FROM recurring_decisions")}


def set_anomaly_review(conn: sqlite3.Connection, transaction_id: int, status: str) -> None:
    with transaction(conn):
        conn.execute(
            """INSERT INTO anomaly_reviews (transaction_id, status, reviewed_at) VALUES (?, ?, ?)
               ON CONFLICT(transaction_id) DO UPDATE SET status = excluded.status,
                                                        reviewed_at = excluded.reviewed_at""",
            (transaction_id, status, now_iso()),
        )


def anomaly_reviews(conn: sqlite3.Connection) -> dict[int, str]:
    return {r["transaction_id"]: r["status"] for r in conn.execute("SELECT * FROM anomaly_reviews")}
