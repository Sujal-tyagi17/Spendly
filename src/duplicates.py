"""Duplicate detection that never deletes legitimate payments by itself.

Two levels:

* **Exact duplicate** — same date, direction, amount, description AND a
  strong key: the running balance or the statement's own transaction ID.
  Two real payments can't leave the account at the same balance (or share a
  transaction ID), so a repeat is a re-extracted row or an overlapping
  statement. These are skipped by default (user can override).
* **Possible duplicate** — same date, direction, amount and merchant but the
  evidence is weaker (no balance column, or different description). Two
  ₹20 chai payments on one day are perfectly normal, so these are imported
  and flagged for the user to review — never removed automatically.
"""

from __future__ import annotations

import hashlib
import sqlite3


def fingerprint(transaction_date: str, direction: str, amount_paise: int,
                description: str, balance_paise: int | None, reference: str | None = None) -> str:
    """Stable hash of the fields that identify one ledger entry.

    ``reference`` is the statement's own transaction ID / UTR when the format
    provides one; it is only ever stored inside this one-way hash.
    """
    key = "|".join([
        transaction_date or "",
        direction or "",
        str(amount_paise),
        " ".join((description or "").upper().split()),
        "" if balance_paise is None else str(balance_paise),
        (reference or "").strip().upper(),
    ])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def _loose_key(row: dict) -> tuple:
    return (row["transaction_date"], row["direction"], row["amount_paise"], row["normalized_merchant"])


def mark_duplicates(rows: list[dict], conn: sqlite3.Connection | None = None) -> list[dict]:
    """Annotate rows in place with ``duplicate_status``:
    "none" | "exact_in_file" | "exact_existing" | "possible".
    """
    existing_fps: set[str] = set()
    existing_loose: set[tuple] = set()
    if conn is not None and rows:
        dates = sorted({r["transaction_date"] for r in rows})
        cur = conn.execute(
            """SELECT fingerprint, transaction_date, direction, amount_paise, normalized_merchant
               FROM transactions WHERE transaction_date BETWEEN ? AND ?""",
            (dates[0], dates[-1]),
        )
        for fp, d, direction, amount, merchant in cur.fetchall():
            existing_fps.add(fp)
            existing_loose.add((d, direction, amount, merchant))

    seen_fps: set[str] = set()
    seen_loose: dict[tuple, int] = {}
    for row in rows:
        fp = row["fingerprint"]
        loose = _loose_key(row)
        strong = bool(row.get("has_strong_key"))
        if fp in existing_fps and strong:
            row["duplicate_status"] = "exact_existing"
        elif fp in seen_fps and strong:
            row["duplicate_status"] = "exact_in_file"
        elif fp in existing_fps or loose in existing_loose or loose in seen_loose:
            row["duplicate_status"] = "possible"
        else:
            row["duplicate_status"] = "none"
        seen_fps.add(fp)
        seen_loose[loose] = seen_loose.get(loose, 0) + 1
    return rows
