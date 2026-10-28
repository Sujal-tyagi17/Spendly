"""Converts raw extracted rows into clean, typed transaction records.

Raw rows come from a parser (PDF) or the sample CSV and are just strings.
This module standardizes:

* dates  -> ISO ``YYYY-MM-DD`` (formats are declared by each parser; we never
  silently guess between day-first and month-first)
* amounts -> integer paise, with a debit/credit direction
* descriptions -> whitespace-collapsed and with identifiers masked

Problems are recorded on the record as ``issues`` instead of raising, so a
single bad row never breaks a whole import.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from src.money import AmountParseError, parse_amount
from src.privacy import mask_sensitive

DEFAULT_DATE_FORMATS = (
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y",
    "%d %b %Y", "%d-%b-%Y", "%d %b %y", "%d-%b-%y", "%d %B %Y",
    "%b %d, %Y", "%Y-%m-%d",
)


@dataclass
class RawRow:
    """A row exactly as extracted, before any interpretation."""

    date_text: str | None
    description: str | None
    debit_text: str | None = None
    credit_text: str | None = None
    amount_text: str | None = None  # single amount column variant
    drcr_text: str | None = None  # "Dr"/"Cr"/"DEBIT"/"CREDIT"
    balance_text: str | None = None
    reference: str | None = None  # transaction ID / UTR, if the format has one
    page: int | None = None
    row_number: int | None = None


@dataclass
class NormalizedRecord:
    row_number: int
    page: int | None
    transaction_date: str | None
    description: str
    direction: str | None
    amount_paise: int | None
    balance_paise: int | None
    reference: str | None = None
    issues: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.issues


class DateParseError(ValueError):
    pass


def parse_date(text: str | None, formats: tuple[str, ...] = DEFAULT_DATE_FORMATS) -> date:
    """Parse a date using only the declared formats.

    If two formats give *different* dates for the same text the value is
    ambiguous and we refuse to guess.
    """
    if text is None or not str(text).strip():
        raise DateParseError("missing date")
    value = " ".join(str(text).split())
    matches: set[date] = set()
    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt).date()
        except ValueError:
            continue
        # "%Y" happily reads "26" as year 0026 — ignore implausible years.
        if 2000 <= parsed.year <= 2100:
            matches.add(parsed)
    if not matches:
        raise DateParseError(f"unrecognised or out-of-range date: {value!r}")
    if len(matches) > 1:
        raise DateParseError(f"ambiguous date: {value!r}")
    return matches.pop()


def _direction_from_text(text: str | None) -> str | None:
    if not text:
        return None
    t = text.strip().lower()
    if t in {"dr", "dr.", "debit", "d", "withdrawal", "paid"}:
        return "debit"
    if t in {"cr", "cr.", "credit", "c", "deposit", "received"}:
        return "credit"
    return None


_EMPTY = {"", "-", "--", "—"}
_ZERO = {"0", "0.0", "0.00"}


def _blank(text: str | None) -> bool:
    """Empty or an explicit zero (a zero in the unused Debit/Credit column is normal)."""
    return text is None or str(text).strip() in _EMPTY | _ZERO


def _is_zero(text: str | None) -> bool:
    return text is not None and str(text).strip() in _ZERO


def normalize_row(row: RawRow, index: int, date_formats: tuple[str, ...] = DEFAULT_DATE_FORMATS) -> NormalizedRecord:
    issues: list[str] = []
    row_number = row.row_number if row.row_number is not None else index + 1

    # Date
    iso_date = None
    try:
        iso_date = parse_date(row.date_text, date_formats).isoformat()
    except DateParseError as exc:
        issues.append(f"Date: {exc}")

    # Description
    description = " ".join((row.description or "").split())
    if not description:
        issues.append("Description: missing")
    description = mask_sensitive(description)

    # Amount + direction
    direction = None
    amount = None
    has_debit = not _blank(row.debit_text)
    has_credit = not _blank(row.credit_text)
    try:
        if has_debit and has_credit:
            issues.append("Amount: both debit and credit are filled")
        elif has_debit or has_credit:
            column_text = row.debit_text if has_debit else row.credit_text
            direction = "debit" if has_debit else "credit"
            if str(column_text).strip().startswith(("-", "(")):
                # A signed value inside a Debit/Credit column is ambiguous (a reversal?).
                # Never guess: report it instead of importing a possibly wrong direction.
                issues.append(f"Amount: negative value in the {direction.title()} column — unclear meaning")
                direction = None
            else:
                amount, _ = parse_amount(column_text)
        elif not _blank(row.amount_text):
            amount, hint = parse_amount(row.amount_text)
            direction = _direction_from_text(row.drcr_text) or hint
            if direction is None:
                issues.append("Amount: cannot tell whether this is a debit or a credit")
        elif any(_is_zero(t) for t in (row.debit_text, row.credit_text, row.amount_text)):
            # An explicit 0.00 is a value, not a gap: report it separately from "missing".
            issues.append("Amount: zero — no money moved")
        else:
            issues.append("Amount: missing")
    except AmountParseError as exc:
        issues.append(f"Amount: {exc}")

    if amount is not None and amount <= 0:
        issues.append("Amount: must be greater than zero")

    balance = None
    if not _blank(row.balance_text):
        try:
            balance, hint = parse_amount(row.balance_text)
            if hint == "debit":  # overdrawn balance shown as "Dr" or negative
                balance = -balance
        except AmountParseError:
            issues.append("Balance: unreadable value")

    return NormalizedRecord(
        row_number=row_number,
        page=row.page,
        transaction_date=iso_date,
        description=description,
        direction=direction,
        amount_paise=amount,
        balance_paise=balance,
        reference=(row.reference or None),
        issues=issues,
    )


def normalize_rows(rows: list[RawRow], date_formats: tuple[str, ...] = DEFAULT_DATE_FORMATS) -> list[NormalizedRecord]:
    return [normalize_row(row, i, date_formats) for i, row in enumerate(rows)]
