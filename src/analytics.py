"""SQL analytics engine.

All metrics are computed in SQLite using the queries in ``sql/``. Each query
starts with

    WITH base AS (SELECT * FROM transactions WHERE 1 = 1 /*FILTERS*/)

and ``build_filter_clause`` swaps ``/*FILTERS*/`` for a parameterized
``AND ...`` clause. Column names in that clause come from fixed code, and
every *value* is passed as a bound parameter, so filters can't inject SQL.

Because every page calls these same functions, a metric such as
"net expenditure" is defined once and means the same thing everywhere.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field, replace
from datetime import date
from functools import lru_cache

import pandas as pd

from src import config


@dataclass(frozen=True)
class Filters:
    start_date: date | None = None
    end_date: date | None = None
    categories: tuple[str, ...] = field(default_factory=tuple)
    transaction_types: tuple[str, ...] = field(default_factory=tuple)
    merchants: tuple[str, ...] = field(default_factory=tuple)
    search: str = ""
    # Review-status filters for the transaction explorer:
    # "needs_review" | "possible_duplicate" | "uncategorized" | "reviewed"
    statuses: tuple[str, ...] = field(default_factory=tuple)

    def without_dates(self) -> "Filters":
        return replace(self, start_date=None, end_date=None)


class FilterError(ValueError):
    pass


def build_filter_clause(filters: Filters | None) -> tuple[str, dict]:
    if filters is None:
        return "", {}
    clauses: list[str] = []
    params: dict = {}
    if filters.start_date and filters.end_date and filters.start_date > filters.end_date:
        raise FilterError("The start date is after the end date.")
    if filters.start_date:
        clauses.append("transaction_date >= :f_start")
        params["f_start"] = filters.start_date.isoformat()
    if filters.end_date:
        clauses.append("transaction_date <= :f_end")
        params["f_end"] = filters.end_date.isoformat()

    for column, values, prefix in (
        ("category", filters.categories, "f_cat"),
        ("transaction_type", filters.transaction_types, "f_type"),
        ("normalized_merchant", filters.merchants, "f_mer"),
    ):
        if values:
            names = [f"{prefix}{i}" for i in range(len(values))]
            clauses.append(f"{column} IN ({', '.join(':' + n for n in names)})")
            params.update(dict(zip(names, values)))

    status_sql = {
        "needs_review": "review_status = 'needs_review'",
        "possible_duplicate": "is_possible_duplicate = 1",
        "uncategorized": "categorization_method = 'none'",
        "reviewed": "review_status = 'reviewed'",
    }
    unknown = set(filters.statuses) - set(status_sql)
    if unknown:
        raise FilterError(f"Unknown status filter: {sorted(unknown)}")
    if filters.statuses:
        # Fixed SQL fragments chosen from a whitelist; no user text reaches the query.
        clauses.append("(" + " OR ".join(status_sql[s] for s in filters.statuses) + ")")

    if filters.search.strip():
        clauses.append("(description LIKE :f_search OR normalized_merchant LIKE :f_search)")
        params["f_search"] = f"%{filters.search.strip()}%"

    clause = "".join(f" AND {c}" for c in clauses)
    return clause, params


@lru_cache(maxsize=None)
def load_sql(name: str) -> str:
    path = config.SQL_DIR / f"{name}.sql"
    return path.read_text(encoding="utf-8")


def run_query(conn: sqlite3.Connection, name: str, filters: Filters | None = None,
              params: dict | None = None) -> pd.DataFrame:
    clause, filter_params = build_filter_clause(filters)
    sql = load_sql(name).replace("/*FILTERS*/", clause)
    return pd.read_sql_query(sql, conn, params={**filter_params, **(params or {})})


# ------------------------------------------------------------- query helpers

def totals(conn, filters: Filters | None = None) -> dict:
    frame = run_query(conn, "totals", filters)
    row = frame.iloc[0].to_dict()
    for key, value in row.items():
        if key.endswith(("_paise", "_count")) and pd.isna(value):
            row[key] = 0
    return row


def monthly_summary(conn, filters: Filters | None = None) -> pd.DataFrame:
    frame = run_query(conn, "monthly_summary", filters)
    if not frame.empty:
        frame["month"] = pd.to_datetime(frame["month_start"])
    return frame


def category_spending(conn, filters: Filters | None = None) -> pd.DataFrame:
    return run_query(conn, "category_spending", filters)


def top_merchants(conn, filters: Filters | None = None, limit: int = 5) -> pd.DataFrame:
    return run_query(conn, "top_merchants", filters, {"limit": int(limit)})


def weekday_spending(conn, filters: Filters | None = None) -> pd.DataFrame:
    return run_query(conn, "weekday_spending", filters)


def largest_transactions(conn, filters: Filters | None = None, limit: int = 10) -> pd.DataFrame:
    return run_query(conn, "largest_transactions", filters, {"limit": int(limit)})


def monthly_category(conn, filters: Filters | None = None) -> pd.DataFrame:
    return run_query(conn, "monthly_category", filters)


def uncategorized(conn, filters: Filters | None = None) -> pd.DataFrame:
    return run_query(conn, "uncategorized", filters)


def refunds_transfers(conn, filters: Filters | None = None) -> pd.DataFrame:
    return run_query(conn, "refunds_transfers", filters)


def recurring_candidates(conn, filters: Filters | None = None, min_occurrences: int = 3) -> pd.DataFrame:
    return run_query(conn, "recurring_candidates", filters, {"min_occurrences": int(min_occurrences)})


def period_change(conn, name: str, filters: Filters | None, current: tuple[date, date],
                  previous: tuple[date, date]) -> pd.DataFrame:
    """``name`` is "category_change" or "merchant_change". Date filters are
    replaced by the two comparison periods."""
    return run_query(conn, name, filters.without_dates() if filters else None, {
        "cur_start": current[0].isoformat(), "cur_end": current[1].isoformat(),
        "prev_start": previous[0].isoformat(), "prev_end": previous[1].isoformat(),
    })


SORTABLE_COLUMNS = {
    "date": "transaction_date",
    "merchant": "normalized_merchant",
    "category": "category",
    "type": "transaction_type",
    # Signed amount so "amount" sorts money-in above money-out.
    "amount": "(CASE WHEN direction = 'credit' THEN amount_paise ELSE -amount_paise END)",
}


def transactions(conn, filters: Filters | None = None, sort: str = "date", descending: bool = True,
                 limit: int | None = None, offset: int = 0) -> pd.DataFrame:
    clause, params = build_filter_clause(filters)
    if sort not in SORTABLE_COLUMNS:
        raise FilterError(f"Cannot sort by {sort!r}")
    direction = "DESC" if descending else "ASC"
    sql = ("SELECT * FROM transactions WHERE 1 = 1" + clause +
           f" ORDER BY {SORTABLE_COLUMNS[sort]} {direction}, id {direction}")
    if limit is not None:
        sql += " LIMIT :_limit OFFSET :_offset"
        params = {**params, "_limit": int(limit), "_offset": int(offset)}
    return pd.read_sql_query(sql, conn, params=params)


def count_transactions(conn, filters: Filters | None = None) -> int:
    clause, params = build_filter_clause(filters)
    return int(conn.execute("SELECT COUNT(*) FROM transactions WHERE 1 = 1" + clause, params).fetchone()[0])


def distinct_values(conn, column: str) -> list[str]:
    if column not in {"category", "normalized_merchant", "transaction_type"}:
        raise ValueError("column not allowed")
    rows = conn.execute(f"SELECT DISTINCT {column} FROM transactions ORDER BY {column}").fetchall()
    return [r[0] for r in rows]


def date_bounds(conn) -> tuple[date | None, date | None]:
    row = conn.execute("SELECT MIN(transaction_date), MAX(transaction_date) FROM transactions").fetchone()
    if not row or row[0] is None:
        return None, None
    return date.fromisoformat(row[0]), date.fromisoformat(row[1])
