"""Import pipeline: raw rows → normalized → validated → categorized → deduplicated → DB.

The same pipeline is used for uploaded PDFs and for the built-in demo CSV,
so the demo exercises exactly the code path real statements go through.

    prepare_* ... builds an ``ImportPreview`` (nothing is written yet)
    commit_import ... writes a preview to SQLite in one database transaction
"""

from __future__ import annotations

import csv
import io
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from src import config, database
from src.categorizer import categorize
from src.data_validator import QualitySummary, summarize
from src.duplicates import fingerprint, mark_duplicates
from src.pdf_parser import ParseResult, file_sha256, parse_statement
from src.privacy import get_logger, mask_sensitive
from src.rules import load_rules
from src.transaction_normalizer import RawRow, normalize_rows

log = get_logger(__name__)


@dataclass
class ImportPreview:
    display_name: str
    file_hash: str
    parser_name: str
    parser_label: str
    period_start: str | None
    period_end: str | None
    rows: list[dict]
    invalid_rows: list[dict]
    quality: QualitySummary
    warnings: list[str] = field(default_factory=list)
    already_imported: bool = False

    # ---- convenient counts for the UI
    @property
    def exact_duplicates(self) -> int:
        return sum(1 for r in self.rows if r["duplicate_status"].startswith("exact"))

    @property
    def possible_duplicates(self) -> int:
        return sum(1 for r in self.rows if r["duplicate_status"] == "possible")

    @property
    def uncategorized(self) -> int:
        return sum(1 for r in self.rows if r["categorization_method"] == "none")

    def to_frame(self) -> pd.DataFrame:
        frame = pd.DataFrame(self.rows)
        if frame.empty:
            return frame
        frame["amount"] = frame["amount_paise"] / 100
        return frame


def _process(records_raw: list[RawRow], parse: ParseResult | None, *, display_name: str,
             file_hash: str, date_formats: tuple[str, ...], conn: sqlite3.Connection | None,
             parser_name: str, parser_label: str, period: tuple[str | None, str | None],
             extra_warnings: list[str]) -> ImportPreview:
    rules = load_rules()
    records = normalize_rows(records_raw, date_formats)
    quality = summarize(records)

    rows: list[dict] = []
    invalid: list[dict] = []
    for record in records:
        if not record.is_valid:
            invalid.append({"row_number": record.row_number, "page": record.page,
                            "reason": "; ".join(record.issues)})
            continue
        result = categorize(record.description, record.direction, rules)
        needs_review = result.needs_review
        rows.append({
            "row_number": record.row_number,
            "page": record.page,
            "transaction_date": record.transaction_date,
            "description": record.description,
            "normalized_merchant": result.merchant,
            "amount_paise": record.amount_paise,
            "direction": record.direction,
            "transaction_type": result.transaction_type,
            "category": result.category,
            "categorization_method": result.method,
            "review_status": "needs_review" if needs_review else "ok",
            "review_reason": result.review_reason,
            "is_transfer": 1 if result.transaction_type == "transfer" else 0,
            "is_possible_duplicate": 0,
            "balance_paise": record.balance_paise,
            "has_strong_key": record.balance_paise is not None or bool(record.reference),
            "fingerprint": fingerprint(record.transaction_date, record.direction, record.amount_paise,
                                       record.description, record.balance_paise, record.reference),
        })

    mark_duplicates(rows, conn)
    for row in rows:
        if row["duplicate_status"] == "possible":
            row["is_possible_duplicate"] = 1
            row["review_status"] = "needs_review"
            row["review_reason"] = "Possible duplicate: same date, amount and merchant as another transaction"

    period_start, period_end = period
    if rows and not period_start:
        period_start = min(r["transaction_date"] for r in rows)
    if rows and not period_end:
        period_end = max(r["transaction_date"] for r in rows)

    already = bool(conn is not None and database.statement_exists(conn, file_hash))
    warnings = list(extra_warnings) + quality.warnings
    if already:
        warnings.insert(0, "This exact file has already been imported. Importing it again is blocked.")

    log.info("Prepared import via %s: %d valid, %d invalid", parser_name, len(rows), len(invalid))
    return ImportPreview(display_name, file_hash, parser_name, parser_label, period_start,
                         period_end, rows, invalid, quality, warnings, already)


def prepare_pdf_import(data: bytes, filename: str, conn: sqlite3.Connection | None,
                       password: str | None = None) -> ImportPreview:
    """Parse a PDF held in memory and build a preview. Raises StatementError
    subclasses with user-friendly messages."""
    parse = parse_statement(data, filename, password)
    return _process(
        parse.rows, parse,
        display_name=mask_sensitive(Path(filename).name),
        file_hash=file_sha256(data),
        date_formats=parse.date_formats,
        conn=conn,
        parser_name=parse.parser_name,
        parser_label=parse.parser_label,
        period=(parse.period_start, parse.period_end),
        extra_warnings=parse.warnings,
    )


def prepare_csv_rows_import(csv_text: str, *, display_name: str, conn: sqlite3.Connection | None,
                            period: tuple[str | None, str | None] = (None, None)) -> ImportPreview:
    """Used for the synthetic demo dataset (columns: date, description, debit, credit, balance)."""
    reader = csv.DictReader(io.StringIO(csv_text))
    raw = [
        RawRow(date_text=r.get("date"), description=r.get("description"), debit_text=r.get("debit"),
               credit_text=r.get("credit"), balance_text=r.get("balance"), row_number=i + 1)
        for i, r in enumerate(reader)
    ]
    return _process(
        raw, None,
        display_name=display_name,
        file_hash=file_sha256(csv_text.encode("utf-8")),
        date_formats=("%Y-%m-%d",),
        conn=conn,
        parser_name="sample_csv",
        parser_label="Synthetic sample dataset (CSV)",
        period=period,
        extra_warnings=[],
    )


def apply_ai_suggestions(preview: ImportPreview, suggestions: dict[str, str]) -> int:
    """Fill uncategorized *debits* with validated AI suggestions. Returns rows changed."""
    changed = 0
    for row in preview.rows:
        category = suggestions.get(row["normalized_merchant"])
        if (category and category in config.CATEGORIES and row["categorization_method"] == "none"
                and row["direction"] == "debit"):
            row["category"] = category
            row["categorization_method"] = "ai"
            row["review_status"] = "needs_review"
            row["review_reason"] = "AI-suggested category — please verify"
            changed += 1
    return changed


def commit_import(conn: sqlite3.Connection, preview: ImportPreview,
                  include_exact_duplicates: bool = False) -> int:
    """Write the preview to the database atomically. Returns the statement id."""
    if preview.already_imported:
        raise ValueError("This file has already been imported.")
    to_insert = [
        r for r in preview.rows
        if include_exact_duplicates or not r["duplicate_status"].startswith("exact")
    ]
    skipped = len(preview.rows) - len(to_insert)

    with database.transaction(conn):
        statement_id = database.insert_statement(
            conn,
            display_name=preview.display_name,
            file_hash=preview.file_hash,
            parser_name=preview.parser_name,
            period_start=preview.period_start,
            period_end=preview.period_end,
            rows_extracted=preview.quality.total_extracted,
            rows_imported=len(to_insert),
            rows_invalid=len(preview.invalid_rows),
            rows_skipped_duplicates=skipped,
            balance_checked_pairs=preview.quality.balance_check.checked_pairs,
            balance_mismatches=preview.quality.balance_check.mismatches,
            warnings=preview.warnings,
        )
        for row in to_insert:
            row["source_statement_id"] = statement_id
        database.insert_transactions(conn, to_insert)
        database.insert_import_issues(conn, statement_id, preview.invalid_rows)
    log.info("Committed statement %d: %d rows imported, %d skipped", statement_id, len(to_insert), skipped)
    return statement_id


def load_demo_dataset(conn: sqlite3.Connection, csv_path: Path = config.SAMPLE_CSV_PATH) -> int:
    """(Re)build the demo database from the synthetic CSV."""
    text = Path(csv_path).read_text(encoding="utf-8")
    dates = sorted(r["date"] for r in csv.DictReader(io.StringIO(text)))
    start = dates[0][:8] + "01" if dates else None
    end = _month_end(dates[-1]) if dates else None
    database.clear_all_data(conn)
    preview = prepare_csv_rows_import(text, display_name="Synthetic demo statement", conn=conn,
                                      period=(start, end))
    statement_id = commit_import(conn, preview)
    from src.budgets import seed_demo_budgets  # local import: budgets depends on analytics
    seed_demo_budgets(conn)
    return statement_id


def _month_end(iso_date: str) -> str:
    ts = pd.Timestamp(iso_date) + pd.offsets.MonthEnd(0)
    return ts.date().isoformat()
