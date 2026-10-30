"""Data-quality dimensions, the per-import validation report and the scorecard.

Every number here is a count produced by the existing validation steps
(normaliser, running-balance check, duplicate detection, categoriser) or a
ratio of two such counts. There is deliberately **no composite quality score**:
completeness, validity, uniqueness, consistency, categorisation coverage and
reconciliation measure different things, and averaging them would hide which
one is weak.

Ratios use this convention:  value = numerator / denominator × 100, rounded to
1 dp, and ``None`` ("n/a") when the denominator is 0 — an empty import has no
completeness, it is not 100% complete.

Reports contain counts, codes and row numbers only — never descriptions,
amounts of individual rows, account numbers or UPI IDs.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from src import database
from src.text import plural

# ------------------------------------------------------------- issue catalogue

@dataclass(frozen=True)
class IssueType:
    code: str
    label: str
    severity: str  # error | warning | info
    dimension: str
    implication: str


# error   = data was not imported, or the totals don't reconcile
# warning = data was imported but may be wrong or double-counted; review it
# info    = a check could not run, or a limitation of the source format
ISSUES: dict[str, IssueType] = {i.code: i for i in [
    IssueType("missing_date", "Missing date", "error", "completeness",
              "The row has no date, so it was not imported. Spending for that day is understated."),
    IssueType("missing_amount", "Missing amount", "error", "completeness",
              "No debit, credit or amount value was found, so the row was not imported."),
    IssueType("missing_description", "Missing description", "error", "completeness",
              "No narration means no merchant or category can be assigned, so the row was not imported."),
    IssueType("ambiguous_date", "Ambiguous date", "error", "validity",
              "The date reads differently day-first and month-first (e.g. 04/05). Spendly never guesses, so the row was not imported."),
    IssueType("invalid_date", "Unreadable date", "error", "validity",
              "The date text doesn't match the statement's date format, so the row was not imported."),
    IssueType("zero_amount", "Zero amount", "error", "validity",
              "The amount is an explicit 0.00. No money moved, so it isn't a transaction and was not imported."),
    IssueType("invalid_amount", "Invalid amount", "error", "validity",
              "The amount is unreadable, negative inside a Debit/Credit column, filled in both columns, or has no direction. Not imported."),
    IssueType("invalid_balance", "Unreadable balance", "error", "validity",
              "The running-balance cell couldn't be read, so the row was not imported."),
    IssueType("exact_duplicate", "Exact duplicate skipped", "info", "uniqueness",
              "Identical to another row including the running balance or transaction ID (e.g. overlapping statements). Skipped so it isn't counted twice."),
    IssueType("possible_duplicate", "Possible duplicate", "warning", "uniqueness",
              "Same date, amount and merchant as another row, without proof it's a copy. Imported and flagged. Two identical payments can be genuine."),
    IssueType("balance_mismatch", "Running-balance mismatch", "warning", "consistency",
              "Previous balance ± amount didn't equal the printed balance. A row may be mis-read, missing or out of order."),
    IssueType("no_balance_column", "No running balance", "info", "consistency",
              "The statement has no balance column (common for UPI apps), so the running-balance check couldn't run."),
    IssueType("reconciliation_difference", "Opening/closing balance doesn't reconcile", "error", "reconciliation",
              "Printed opening balance + credits − debits ≠ printed closing balance. Rows are probably missing or mis-read."),
    IssueType("uncategorised", "Uncategorised", "warning", "categorisation",
              "No rule matched the merchant. The row counts as “Other” in category analysis until you set a category."),
    IssueType("unknown_merchant", "Merchant not recognised", "warning", "categorisation",
              "Merchant normalisation produced “Unknown”, so merchant-level analysis can't use these rows."),
]}

# Primary reason for a rejected row (first match wins), so each row is counted once.
_REJECT_PRIORITY = ["missing_date", "missing_amount", "missing_description", "ambiguous_date", "invalid_date",
                    "zero_amount", "invalid_amount", "invalid_balance"]
_MISSING = {"missing_date", "missing_amount", "missing_description"}


def classify_issue(text: str) -> str:
    """Map a normaliser issue string to a stable issue code."""
    field, _, detail = text.partition(":")
    field, detail = field.strip().lower(), detail.strip().lower()
    if field == "date":
        if detail.startswith("missing"):
            return "missing_date"
        return "ambiguous_date" if "ambiguous" in detail else "invalid_date"
    if field == "description":
        return "missing_description"
    if field == "amount":
        if detail.startswith("missing"):
            return "missing_amount"
        return "zero_amount" if detail.startswith("zero") else "invalid_amount"
    if field == "balance":
        return "invalid_balance"
    return "invalid_amount"


def row_codes(reason: str) -> list[str]:
    return [classify_issue(part) for part in reason.split("; ") if part.strip()]


def primary_code(codes: list[str]) -> str:
    return min(codes, key=lambda c: _REJECT_PRIORITY.index(c) if c in _REJECT_PRIORITY else 99)


def pct(numerator: int, denominator: int) -> float | None:
    return round(100 * numerator / denominator, 1) if denominator else None


# ------------------------------------------------------------ import report

def import_report(preview, include_exact_duplicates: bool = False) -> dict:
    """Structured validation report for one import (built from the preview, so it
    is the same before and after confirmation).

    Row buckets are mutually exclusive and add up:
        rows_extracted = rows_rejected + rows_accepted
        rows_accepted  = rows_to_import + exact_duplicates_skipped
    Flags (possible duplicates, uncategorised, …) are counted on accepted rows and
    can overlap, so they are never added together.
    """
    q = preview.quality
    rejected_by_reason = {code: 0 for code in _REJECT_PRIORITY}
    field_issues = {code: 0 for code in _REJECT_PRIORITY}
    incomplete = 0
    for row in preview.invalid_rows:
        codes = row_codes(row["reason"])
        rejected_by_reason[primary_code(codes)] += 1
        for code in set(codes):
            field_issues[code] += 1
        if _MISSING & set(codes):
            incomplete += 1

    rows = preview.rows
    exact = sum(1 for r in rows if r["duplicate_status"].startswith("exact"))
    skipped = 0 if include_exact_duplicates else exact
    accepted = len(rows)
    extracted = q.total_extracted
    complete = extracted - incomplete
    balance = q.balance_check
    rec = preview.reconciliation
    flags = {
        "possible_duplicates": sum(1 for r in rows if r["duplicate_status"] == "possible"),
        "uncategorised": sum(1 for r in rows if r["categorization_method"] == "none"),
        "unknown_merchant": sum(1 for r in rows if r["normalized_merchant"] == "Unknown"),
        "needs_review": sum(1 for r in rows if r["review_status"] == "needs_review"),
        "balance_mismatch_rows": len(balance.mismatch_rows),
        "rows_without_balance": sum(1 for r in rows if r["balance_paise"] is None),
    }
    report = {
        "rows_extracted": extracted,
        "rows_rejected": len(preview.invalid_rows),
        "rows_accepted": accepted,
        "rows_to_import": accepted - skipped,
        "exact_duplicates_skipped": skipped,
        "exact_duplicates_found": exact,
        "rejected_by_reason": rejected_by_reason,
        "field_issues": field_issues,
        "rows_complete": complete,
        "flags": flags,
        "balance_check": {"available": balance.available, "checked_pairs": balance.checked_pairs,
                          "mismatches": balance.mismatches, "order": balance.order,
                          "mismatch_rows": balance.mismatch_rows[:50]},
        "reconciliation": rec.as_dict(),
        "dimensions": {
            "completeness_pct": pct(complete, extracted),
            "validity_pct": pct(accepted, complete),
            "uniqueness_pct": pct(accepted - exact, accepted),
            "balance_consistency_pct": pct(balance.checked_pairs - balance.mismatches, balance.checked_pairs),
            "categorisation_coverage_pct": pct(accepted - flags["uncategorised"], accepted),
        },
        "warnings": list(preview.warnings),
    }
    report["issues"] = _issue_list(report)
    return report


def _issue_list(report: dict) -> list[dict]:
    """Issue items with counts > 0 (or informational ones), each with severity and implication."""
    counts = dict(report["rejected_by_reason"])
    counts["exact_duplicate"] = report["exact_duplicates_found"]
    counts["possible_duplicate"] = report["flags"]["possible_duplicates"]
    counts["balance_mismatch"] = report["balance_check"]["mismatches"]
    counts["uncategorised"] = report["flags"]["uncategorised"]
    counts["unknown_merchant"] = report["flags"]["unknown_merchant"]
    # Only when no accepted row has a balance at all (one row with a balance is not "no balance column").
    counts["no_balance_column"] = (1 if report["rows_accepted"]
                                   and report["flags"]["rows_without_balance"] == report["rows_accepted"] else 0)
    rec = report["reconciliation"]
    counts["reconciliation_difference"] = 1 if rec["available"] and rec["difference_paise"] != 0 else 0
    items = []
    for code, n in counts.items():
        if n:
            t = ISSUES[code]
            items.append({"code": code, "label": t.label, "severity": t.severity, "dimension": t.dimension,
                          "count": n, "implication": t.implication,
                          "unit": "statement" if code in {"no_balance_column", "reconciliation_difference"} else "rows"})
    order = {"error": 0, "warning": 1, "info": 2}
    return sorted(items, key=lambda i: (order[i["severity"]], -i["count"]))


# ---------------------------------------------------------------- scorecard

def _metric(key, label, numerator, denominator, definition, *, note=None, higher_is_better=True):
    return {"key": key, "label": label, "numerator": numerator, "denominator": denominator,
            "value_pct": pct(numerator, denominator), "definition": definition, "note": note,
            "higher_is_better": higher_is_better}


def scorecard(conn: sqlite3.Connection, statement_id: int | None = None) -> dict:
    """Quality dimensions for all imports (or one), from stored import reports
    (extraction-time facts) and the transactions table (current state, after edits)."""
    statements = database.list_statements(conn)
    if statement_id is not None:
        statements = [s for s in statements if s["id"] == statement_id]
    with_report = [s for s in statements if s["quality_report"]]
    reports = [s["quality_report"] for s in with_report]

    def total(key, sub=None):
        return sum((r[key][sub] if sub else r[key]) for r in reports)

    extracted = total("rows_extracted")
    complete = total("rows_complete")
    accepted = total("rows_accepted")
    exact = total("exact_duplicates_found")
    pairs = sum(s["balance_checked_pairs"] for s in statements)
    mismatches = sum(s["balance_mismatches"] for s in statements)
    rec_available = [r["reconciliation"] for r in reports if r["reconciliation"]["available"]]
    reconciled = sum(1 for r in rec_available if r["difference_paise"] == 0)

    where, params = ("WHERE source_statement_id = ?", (statement_id,)) if statement_id is not None else ("", ())
    row = conn.execute(
        f"""SELECT COUNT(*) AS n,
                   SUM(categorization_method != 'none') AS categorised,
                   SUM(is_possible_duplicate = 1) AS possible,
                   SUM(balance_paise IS NOT NULL) AS with_balance,
                   SUM(balance_check = 'mismatch') AS mismatch_rows,
                   SUM(normalized_merchant = 'Unknown') AS unknown_merchant,
                   SUM(review_status = 'needs_review') AS needs_review
            FROM transactions {where}""", params).fetchone()  # noqa: S608 - fixed fragment
    n = int(row["n"] or 0)
    methods = {r[0]: int(r[1]) for r in conn.execute(
        f"SELECT categorization_method, COUNT(*) FROM transactions {where} GROUP BY 1", params)}  # noqa: S608

    dimensions = [
        _metric("completeness", "Completeness", complete, extracted,
                "Extracted rows with a date, an amount and a description ÷ all extracted rows.",
                note=None if len(reports) == len(statements) else
                f"{plural(len(statements) - len(reports), 'older import')} without a stored report "
                f"{'is' if len(statements) - len(reports) == 1 else 'are'} excluded."),
        _metric("validity", "Validity", accepted, complete,
                "Complete rows that pass every field and business rule (readable unambiguous date, positive amount "
                "with a clear direction, readable balance) ÷ complete rows."),
        _metric("uniqueness", "Uniqueness", accepted - exact, accepted,
                "Accepted rows that are not exact duplicates ÷ accepted rows. Possible duplicates are reported "
                "separately and are NOT counted as duplicates.",
                note=f"{plural(row['possible'] or 0, 'possible duplicate')} currently flagged for review."),
        _metric("consistency", "Running-balance consistency", pairs - mismatches, pairs,
                "Consecutive row pairs where previous balance ± amount = printed balance ÷ pairs that could be checked.",
                note=None if pairs else "No statement had a running-balance column, so this couldn't be measured."),
        _metric("categorisation", "Categorisation coverage", int(row["categorised"] or 0), n,
                "Saved transactions with a category from a rule, merchant match, AI suggestion or manual edit ÷ "
                "saved transactions. Reflects your corrections since import.",
                note=f"{methods.get('ai', 0)} AI-suggested (still to verify)." if methods.get("ai") else None),
        _metric("reconciliation", "Statement reconciliation", reconciled, len(rec_available),
                "Statements where printed opening balance + credits − debits = printed closing balance ÷ statements "
                "that print both balances.",
                note=None if rec_available else "No statement printed both an opening and a closing balance."),
    ]

    breakdown = {}
    for r in reports:
        for item in r["issues"]:
            b = breakdown.setdefault(item["code"], {**{k: item[k] for k in ("code", "label", "severity", "dimension",
                                                                         "implication", "unit")}, "count": 0})
            b["count"] += item["count"]
    current = {
        "possible_duplicate": int(row["possible"] or 0),
        "uncategorised": n - int(row["categorised"] or 0),
        "unknown_merchant": int(row["unknown_merchant"] or 0),
        "balance_mismatch": int(row["mismatch_rows"] or 0),
    }
    links = {"possible_duplicate": "possible_duplicate", "uncategorised": "uncategorized",
             "unknown_merchant": "unknown_merchant", "balance_mismatch": "balance_mismatch"}
    order = {"error": 0, "warning": 1, "info": 2}
    issues = []
    for code, b in breakdown.items():
        b["current_count"] = current.get(code)  # how many saved rows still carry the flag (None = not per-row)
        b["status_filter"] = links.get(code)
        issues.append(b)
    issues.sort(key=lambda i: (order[i["severity"]], -i["count"]))

    trend = [{
        "statement_id": s["id"], "display_name": s["display_name"], "imported_at": s["created_at"],
        "rows_extracted": s["quality_report"]["rows_extracted"],
        "rows_rejected": s["quality_report"]["rows_rejected"],
        "exact_duplicates": s["quality_report"]["exact_duplicates_found"],
        "possible_duplicates": s["quality_report"]["flags"]["possible_duplicates"],
        "balance_mismatches": s["quality_report"]["balance_check"]["mismatches"],
        "uncategorised": s["quality_report"]["flags"]["uncategorised"],
        "completeness_pct": s["quality_report"]["dimensions"]["completeness_pct"],
        "validity_pct": s["quality_report"]["dimensions"]["validity_pct"],
    } for s in with_report]

    return {
        "scope": {"statement_id": statement_id, "statements": len(statements), "with_report": len(reports),
                  "transactions": n},
        "dimensions": dimensions,
        "issues": issues,
        "categorisation_methods": methods,
        "rows_with_balance": int(row["with_balance"] or 0),
        "trend": trend,
        "trend_available": len(trend) >= 2,
        "statements": [{"id": s["id"], "display_name": s["display_name"], "parser_name": s["parser_name"],
                        "period_start": s["statement_period_start"], "period_end": s["statement_period_end"],
                        "imported_at": s["created_at"], "report": s["quality_report"]} for s in statements],
    }
