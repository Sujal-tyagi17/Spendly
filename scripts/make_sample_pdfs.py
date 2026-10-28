"""Create the synthetic sample PDF statements in data/sample_statements/.

* sample_bank_statement.pdf    — bank-table layout, Jul–Aug 2026 (multi-page)
* sample_phonepe_statement.pdf — PhonePe-style layout, UPI payments in Sep 2026

Both are built from data/sample_transactions.csv, so every value is synthetic.
Usage:  python scripts/make_sample_pdfs.py   (needs requirements-dev.txt)
"""

from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.merchant_normalizer import normalize_merchant  # noqa: E402
from src.sample_pdfs import bank_statement_pdf, phonepe_statement_pdf  # noqa: E402

OUT_DIR = ROOT / "data" / "sample_statements"


def paise(text: str) -> int | None:
    return round(float(text) * 100) if text else None


def main() -> None:
    rows = [r for r in csv.DictReader(open(ROOT / "data" / "sample_transactions.csv", encoding="utf-8"))
            if r["truth_type"] != "duplicate"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    bank_rows = [
        {"date": date.fromisoformat(r["date"]), "description": r["description"],
         "debit": paise(r["debit"]), "credit": paise(r["credit"]), "balance": paise(r["balance"])}
        for r in rows if "2026-07-01" <= r["date"] <= "2026-08-31"
    ]
    (OUT_DIR / "sample_bank_statement.pdf").write_bytes(
        bank_statement_pdf(bank_rows, period=(date(2026, 7, 1), date(2026, 8, 31)))
    )

    upi_rows = []
    for i, r in enumerate(x for x in rows if x["date"] >= "2026-09-01" and x["description"].startswith("UPI/")):
        merchant = normalize_merchant(r["description"]).merchant
        direction = "debit" if r["debit"] else "credit"
        upi_rows.append({
            "date": date.fromisoformat(r["date"]),
            "details": f"Paid to {merchant}" if direction == "debit" else f"Received from {merchant}",
            "direction": direction,
            "amount": paise(r["debit"] or r["credit"]),
            "txn_id": f"T2609{i:010d}",
        })
    upi_rows.reverse()  # PhonePe lists newest first
    (OUT_DIR / "sample_phonepe_statement.pdf").write_bytes(
        phonepe_statement_pdf(upi_rows, period=(date(2026, 9, 1), date(2026, 9, 30)))
    )
    print(f"Wrote {len(bank_rows)} bank rows and {len(upi_rows)} PhonePe rows to {OUT_DIR}")


if __name__ == "__main__":
    main()
