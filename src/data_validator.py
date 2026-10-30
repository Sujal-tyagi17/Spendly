"""Data-quality checks run on normalized records before import.

Besides per-row issues (bad dates, missing amounts) we run a **running
balance check**: when a statement has a balance column, every row should
satisfy ``previous_balance - debit + credit == balance``. A mismatch usually
means a row was mis-extracted (e.g. a wrapped line was read as two rows), so
it is a cheap and powerful way to tell users how much to trust an import.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.text import plural
from src.transaction_normalizer import NormalizedRecord


@dataclass
class BalanceCheck:
    checked_pairs: int = 0
    mismatches: int = 0
    order: str | None = None  # "oldest_first" | "newest_first"
    mismatch_rows: list[int] = field(default_factory=list)
    checked_rows: list[int] = field(default_factory=list)  # rows compared with the row before them
    repeated_rows_skipped: int = 0

    @property
    def available(self) -> bool:
        return self.checked_pairs > 0

    @property
    def match_rate(self) -> float | None:
        if not self.checked_pairs:
            return None
        return (self.checked_pairs - self.mismatches) / self.checked_pairs


def _signed(record: NormalizedRecord) -> int:
    return record.amount_paise if record.direction == "credit" else -record.amount_paise


def _same_entry(a: NormalizedRecord, b: NormalizedRecord) -> bool:
    return (a.transaction_date, a.direction, a.amount_paise, a.description, a.balance_paise) == \
           (b.transaction_date, b.direction, b.amount_paise, b.description, b.balance_paise)


def _check_order(records: list[NormalizedRecord]) -> BalanceCheck:
    result = BalanceCheck()
    previous = None
    for record in records:
        if record.balance_paise is None or record.amount_paise is None or record.direction is None:
            previous = None
            continue
        if previous is not None and _same_entry(previous, record):
            # A row repeated verbatim (same balance too) is a re-extracted copy. It is
            # reported once, as an exact duplicate, not a second time as a balance break.
            result.repeated_rows_skipped += 1
            continue
        if previous is not None:
            result.checked_pairs += 1
            result.checked_rows.append(record.row_number)
            if previous.balance_paise + _signed(record) != record.balance_paise:
                result.mismatches += 1
                result.mismatch_rows.append(record.row_number)
        previous = record
    return result


def check_running_balance(records: list[NormalizedRecord]) -> BalanceCheck:
    """Try both chronological orders (statements are printed either way)."""
    valid = [r for r in records if r.is_valid]
    forward = _check_order(valid)
    forward.order = "oldest_first"
    backward = _check_order(list(reversed(valid)))
    backward.order = "newest_first"
    if not forward.available:
        return forward
    return forward if forward.mismatches <= backward.mismatches else backward


@dataclass
class Reconciliation:
    """Printed opening balance + credits − debits, compared with the printed closing balance."""
    opening_paise: int | None
    closing_paise: int | None
    credits_paise: int = 0
    debits_paise: int = 0

    @property
    def available(self) -> bool:
        return self.opening_paise is not None and self.closing_paise is not None

    @property
    def computed_closing_paise(self) -> int | None:
        return self.opening_paise + self.credits_paise - self.debits_paise if self.available else None

    @property
    def difference_paise(self) -> int | None:
        """computed − printed closing; 0 means the extracted rows fully explain the movement."""
        return self.computed_closing_paise - self.closing_paise if self.available else None

    def as_dict(self) -> dict:
        return {"available": self.available, "opening_paise": self.opening_paise, "closing_paise": self.closing_paise,
                "credits_paise": self.credits_paise, "debits_paise": self.debits_paise,
                "computed_closing_paise": self.computed_closing_paise, "difference_paise": self.difference_paise,
                "reconciled": None if not self.available else self.difference_paise == 0}


def reconcile(rows: list[dict], opening: int | None, closing: int | None) -> Reconciliation:
    """``rows`` are accepted rows of ONE statement (exact copies within the same file excluded)."""
    result = Reconciliation(opening, closing)
    for r in rows:
        if r["direction"] == "credit":
            result.credits_paise += r["amount_paise"]
        else:
            result.debits_paise += r["amount_paise"]
    return result


@dataclass
class QualitySummary:
    total_extracted: int
    valid: int
    invalid: int
    issue_counts: dict[str, int]
    balance_check: BalanceCheck
    warnings: list[str]


def summarize(records: list[NormalizedRecord]) -> QualitySummary:
    issue_counts: dict[str, int] = {}
    for record in records:
        for issue in record.issues:
            key = issue.split(":", 1)[0]
            issue_counts[key] = issue_counts.get(key, 0) + 1

    valid = sum(1 for r in records if r.is_valid)
    balance = check_running_balance(records)
    warnings = []
    if not records:
        warnings.append("No transaction rows were found in this file.")
    if records and valid < len(records):
        warnings.append(f"{plural(len(records) - valid, 'row')} could not be read and will not be imported.")
    if balance.available and balance.mismatches:
        warnings.append(
            f"Running balance did not add up on {balance.mismatches} of {balance.checked_pairs} "
            "consecutive rows — some rows may have been extracted incorrectly or be missing."
        )
    with_balance = sum(1 for r in records if r.is_valid and r.balance_paise is not None)
    if not balance.available and records:
        if with_balance == 0:
            warnings.append("No balance column found, so extraction completeness could not be cross-checked.")
        else:
            warnings.append("The running-balance check needs at least two consecutive rows with a balance, "
                            "so it couldn't run for this statement.")

    return QualitySummary(
        total_extracted=len(records),
        valid=valid,
        invalid=len(records) - valid,
        issue_counts=issue_counts,
        balance_check=balance,
        warnings=warnings,
    )
