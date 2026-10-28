"""Repeatable evaluation of the PDF parsers against statements with known contents.

This measures **parser accuracy** (did we read what is printed?), which is a
different question from the data-quality dimensions in ``src/quality.py``
(is the data that was read complete, valid and consistent?).

Ground truth is what is *printed* in the PDF, one row per transaction:
date, description, direction, amount and (if printed) balance.

Matching methodology
--------------------
1. Extracted rows are normalised exactly as an import would (``normalize_rows``).
   Rows the normaliser rejects are kept as extracted-but-invalid (their fields
   count as wrong).
2. Expected and extracted rows are aligned **in statement order** with
   ``difflib.SequenceMatcher`` on the key (date, direction, amount). Matching
   blocks pair up directly; "replace" blocks of equal length are paired
   position by position, so a row whose date was misread still pairs with its
   expected counterpart and is scored as a date error. Anything left unpaired is
   a missed (expected) or spurious (extracted) row.
3. Field metrics use **expected rows** as the denominator, so a missed row counts
   as wrong for every field.

Metrics (``None`` when the denominator is 0)
    count_agreement        extracted rows == expected rows (and both numbers)
    date_accuracy          paired rows with the exact date ÷ expected rows
    amount_accuracy        paired rows with the exact amount AND direction ÷ expected rows
    description_exact      paired rows whose masked description equals the expected one ÷ expected rows
    description_similarity mean token Jaccard similarity over expected rows (unpaired = 0)
    balance_reconciliation running-balance pairs that add up ÷ pairs checked (statements with a balance column)
    missed_rows / spurious_rows

Fixtures
--------
``synthetic_fixtures()`` builds PDFs with ``src.sample_pdfs`` (synthetic layouts
that imitate common formats, not copies of a real bank's statement). Real
statements can be added locally to ``data/parser_eval/real/`` as
``<name>.pdf`` + ``<name>.expected.csv`` (columns: date, description,
direction, amount, balance). Only use statements whose owner consented, with
identifiers removed; the folder is git-ignored and nothing is ever uploaded.
Until representative real statements have been evaluated, results describe the
synthetic layouts only and say nothing about real-world accuracy.
"""

from __future__ import annotations

import csv
import difflib
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from src import config
from src.data_validator import check_running_balance
from src.money import parse_amount
from src.pdf_parser import parse_statement
from src.privacy import mask_sensitive
from src.transaction_normalizer import normalize_rows

REAL_DIR = config.DATA_DIR / "parser_eval" / "real"


@dataclass
class ExpectedRow:
    date: str  # ISO
    description: str
    direction: str
    amount_paise: int
    balance_paise: int | None = None


@dataclass
class Fixture:
    name: str
    kind: str  # "synthetic" | "real"
    layout: str
    pdf: bytes
    expected: list[ExpectedRow]
    notes: str = ""
    characteristics: list[str] = field(default_factory=list)


def _tokens(text: str) -> set[str]:
    return set(" ".join((text or "").upper().replace("/", " ").split()).split())


def jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta and not tb:
        return 1.0
    return len(ta & tb) / len(ta | tb)


def _ratio(n: int, d: int) -> float | None:
    return round(100 * n / d, 1) if d else None


def evaluate(fixture: Fixture) -> dict:
    parsed = parse_statement(fixture.pdf, f"{fixture.name}.pdf")
    records = normalize_rows(parsed.rows, parsed.date_formats)
    got = [(r.transaction_date, r.direction, r.amount_paise) for r in records]
    want = [(e.date, e.direction, e.amount_paise) for e in fixture.expected]

    pairs: list[tuple[int, int]] = []
    matcher = difflib.SequenceMatcher(a=want, b=got, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal" or (tag == "replace" and i2 - i1 == j2 - j1):
            pairs.extend(zip(range(i1, i2), range(j1, j2)))
    n = len(fixture.expected)
    date_ok = amount_ok = desc_exact = 0
    similarity = 0.0
    for i, j in pairs:
        e, r = fixture.expected[i], records[j]
        date_ok += r.transaction_date == e.date
        amount_ok += (r.amount_paise == e.amount_paise and r.direction == e.direction)
        expected_desc = " ".join(mask_sensitive(e.description).split())
        desc_exact += r.description == expected_desc
        similarity += jaccard(r.description, expected_desc)
    balance = check_running_balance(records)
    return {
        "fixture": fixture.name, "kind": fixture.kind, "layout": fixture.layout, "parser": parsed.parser_name,
        "pages": parsed.page_count, "characteristics": fixture.characteristics,
        "expected_rows": n, "extracted_rows": len(records), "count_agreement": len(records) == n,
        "paired_rows": len(pairs), "missed_rows": n - len(pairs), "spurious_rows": len(records) - len(pairs),
        "date_accuracy_pct": _ratio(date_ok, n), "amount_accuracy_pct": _ratio(amount_ok, n),
        "description_exact_pct": _ratio(desc_exact, n),
        "description_similarity_pct": round(100 * similarity / n, 1) if n else None,
        "balance_pairs_checked": balance.checked_pairs,
        "balance_reconciliation_pct": _ratio(balance.checked_pairs - balance.mismatches, balance.checked_pairs),
    }


def summarise(results: list[dict]) -> dict:
    """Pooled totals (row-weighted), kept separate for synthetic and real fixtures."""
    out = {}
    for kind in ("synthetic", "real"):
        rs = [r for r in results if r["kind"] == kind]
        n = sum(r["expected_rows"] for r in rs)

        def pooled(key):
            return round(sum((r[key] or 0) * r["expected_rows"] for r in rs) / n, 1) if n else None
        pairs = sum(r["balance_pairs_checked"] for r in rs)
        out[kind] = {
            "fixtures": len(rs), "expected_rows": n,
            "count_agreement": f"{sum(r['count_agreement'] for r in rs)}/{len(rs)}" if rs else None,
            "date_accuracy_pct": pooled("date_accuracy_pct"), "amount_accuracy_pct": pooled("amount_accuracy_pct"),
            "description_exact_pct": pooled("description_exact_pct"),
            "description_similarity_pct": pooled("description_similarity_pct"),
            "balance_reconciliation_pct": round(sum((r["balance_reconciliation_pct"] or 0) * r["balance_pairs_checked"]
                                                    for r in rs) / pairs, 1) if pairs else None,
        }
    return out


# ------------------------------------------------------------------ fixtures

_MERCHANTS = ["UPI/DR/{ref}/ZOMATO/YESB/zomato@ybl/Payment", "UPI/DR/{ref}/BLINKIT/YESB/blinkit@hdfcbank/Payment",
              "POS/XXXX4521/AMAZON PAY INDIA", "UPI/DR/{ref}/UBER INDIA/YESB", "ACH/DR/{ref}/NETFLIX.COM",
              "UPI/DR/{ref}/SWIGGY/YESB/swiggy@axisbank", "BILLDESK/AIRTEL POSTPAID"]


def _bank_rows(n: int, seed: int, start=date(2026, 7, 1), refunds: int = 0):
    rng = random.Random(seed)
    balance, rows = 1_50_000_00, []
    day = start
    for i in range(n):
        day += timedelta(days=rng.choice([0, 0, 1, 1, 2]))
        if refunds and i % max(2, n // refunds) == 1:
            amount, desc, credit = rng.randint(100, 2000) * 100, f"UPI/CR/{700000 + i}/AMAZON REFUND/UTIB", True
        elif i % 25 == 0:
            amount, desc, credit = 85_000_00, f"NEFT/CR/{800000 + i}/ACME TECH/SALARY", True
        else:
            amount = rng.randint(40, 4500) * 100 + rng.choice([0, 50])
            desc, credit = rng.choice(_MERCHANTS).format(ref=600000000000 + i), False
        balance += amount if credit else -amount
        rows.append({"date": day, "description": desc, "debit": None if credit else amount,
                     "credit": amount if credit else None, "balance": balance})
    return rows


def _expected_from_bank(rows, wrap_first=False) -> list[ExpectedRow]:
    out = []
    for i, r in enumerate(rows):
        desc = r["description"][:58]
        if wrap_first and i == 0:
            desc = f"{desc} (continued) REMARKS: MONTHLY PAYMENT"
        out.append(ExpectedRow(r["date"].isoformat(), desc, "credit" if r["credit"] else "debit",
                               r["credit"] or r["debit"], r["balance"]))
    return out


def synthetic_fixtures() -> list[Fixture]:
    from src.sample_pdfs import (  # reportlab: dev dependency
        bank_statement_pdf,
        phonepe_statement_pdf,
    )
    fixtures = []
    rows = _bank_rows(12, seed=1)
    opening = rows[0]["balance"] + (rows[0]["debit"] or 0) - (rows[0]["credit"] or 0)
    fixtures.append(Fixture("bank_single_page", "synthetic", "Bank table (Withdrawal/Deposit/Balance)",
                            bank_statement_pdf(rows, period=(date(2026, 7, 1), date(2026, 7, 31)),
                                               opening_balance=opening, closing_balance=rows[-1]["balance"]),
                            _expected_from_bank(rows), characteristics=["running balance", "printed opening/closing"]))
    rows = _bank_rows(140, seed=2)
    fixtures.append(Fixture("bank_multi_page", "synthetic", "Bank table (Withdrawal/Deposit/Balance)",
                            bank_statement_pdf(rows), _expected_from_bank(rows),
                            characteristics=["multi-page", "repeated headers", "running balance"]))
    rows = _bank_rows(15, seed=3)
    fixtures.append(Fixture("bank_wrapped_description", "synthetic", "Bank table (Withdrawal/Deposit/Balance)",
                            bank_statement_pdf(rows, wrap_first_description=True), _expected_from_bank(rows, True),
                            characteristics=["wrapped narration line", "running balance"]))
    rows = _bank_rows(30, seed=4, refunds=6)
    fixtures.append(Fixture("bank_with_refunds", "synthetic", "Bank table (Withdrawal/Deposit/Balance)",
                            bank_statement_pdf(rows), _expected_from_bank(rows),
                            characteristics=["refund credits", "running balance"]))
    rng = random.Random(5)
    pp, day = [], date(2026, 8, 1)
    for i in range(36):
        day += timedelta(days=rng.choice([0, 1, 1, 2]))
        debit = i % 7 != 3
        name = rng.choice(["Zomato", "Blinkit", "Rapido", "Swiggy", "BookMyShow"]) if debit else "Rahul Sharma"
        pp.append({"date": day, "details": f"Paid to {name}" if debit else f"Received from {name}",
                   "direction": "debit" if debit else "credit", "amount": rng.randint(20, 1500) * 100,
                   "txn_id": f"T26080{i:010d}"})
    fixtures.append(Fixture("phonepe_no_balance", "synthetic", "PhonePe app statement",
                            phonepe_statement_pdf(pp, period=(date(2026, 8, 1), day)),
                            [ExpectedRow(r["date"].isoformat(), r["details"], r["direction"], r["amount"]) for r in pp],
                            characteristics=["no running balance", "transaction IDs", "multi-page"]))
    return fixtures


def real_fixtures(directory: Path = REAL_DIR) -> list[Fixture]:
    """Locally supplied, consented and anonymised statements (never committed)."""
    out = []
    if not directory.exists():
        return out
    for pdf in sorted(directory.glob("*.pdf")):
        truth = pdf.with_suffix(".expected.csv")
        if not truth.exists():
            continue
        expected = []
        with truth.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                balance = parse_amount(r["balance"])[0] if r.get("balance") else None
                expected.append(ExpectedRow(r["date"], r["description"], r["direction"],
                                            parse_amount(r["amount"])[0], balance))
        out.append(Fixture(pdf.stem, "real", "real statement", pdf.read_bytes(), expected))
    return out


def run_all(include_real: bool = True) -> tuple[list[dict], dict]:
    fixtures = synthetic_fixtures() + (real_fixtures() if include_real else [])
    results = [evaluate(f) for f in fixtures]
    return results, summarise(results)
