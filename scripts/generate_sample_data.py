"""Generate the synthetic demo dataset: data/sample_transactions.csv

Every row is invented. No real person, account or transaction is represented.
The generator is seeded, so running it again produces the identical file.

Columns
-------
date, description, debit, credit, balance   -> what a bank statement contains
truth_type, truth_category                   -> ground-truth labels, used ONLY by
                                                the test-suite to check that the
                                                pipeline classifies rows correctly
                                                (the app ignores these columns)

Usage:  python scripts/generate_sample_data.py
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 17
START = date(2026, 4, 1)
MONTHS = 6  # April – September 2026
OPENING_BALANCE = 85_000_00  # paise
OUT = Path(__file__).resolve().parent.parent / "data" / "sample_transactions.csv"

rng = random.Random(SEED)
_ref_counter = 0


def ref() -> str:
    global _ref_counter
    _ref_counter += 1
    return f"6{_ref_counter:011d}"


def upi_dr(name: str, handle: str, bank: str = "YESB") -> str:
    return f"UPI/DR/{ref()}/{name}/{bank}/{handle}/Payment"


def upi_cr(name: str, handle: str, bank: str = "HDFC") -> str:
    return f"UPI/CR/{ref()}/{name}/{bank}/{handle}/Payment"


def month_start(i: int) -> date:
    y, m = START.year, START.month + i
    while m > 12:
        y, m = y + 1, m - 12
    return date(y, m, 1)


def days_in_month(d: date) -> int:
    nxt = month_start((d.year - START.year) * 12 + d.month - START.month + 1)
    return (nxt - d).days


def rupees(lo: int, hi: int, step: int = 1) -> int:
    return rng.randrange(lo, hi + 1, step) * 100


events: list[dict] = []


def add(d: date, description: str, amount: int, direction: str, truth_type: str, truth_category: str):
    events.append(dict(date=d, description=description, amount=amount, direction=direction,
                       truth_type=truth_type, truth_category=truth_category))


for i in range(MONTHS):
    m0 = month_start(i)
    dim = days_in_month(m0)
    day = lambda n: m0 + timedelta(days=min(n, dim) - 1)  # noqa: E731
    month_label = m0.strftime("%b %Y").upper()

    # ---- income
    add(day(1), f"NEFT/CR/{ref()}/ACME ANALYTICS PVT LTD/SALARY {month_label}", 65_000_00,
        "credit", "income", "Income")

    # ---- fixed outflows
    add(day(3), f"IMPS/DR/{ref()}/HOUSE RENT/MR K NAIR", 18_000_00, "debit", "expense", "Rent & Housing")
    add(day(2), f"IMPS/DR/{ref()}/SELF TRANSFER TO OWN A/C XXXXXX4521", 10_000_00, "debit", "transfer", "Transfers")
    add(day(18), f"BILLDESK/CREDIT CARD PAYMENT/HDFC CARD XXXX9012", rupees(5_500, 9_000, 50),
        "debit", "cc_repayment", "Transfers")
    add(day(rng.randint(7, 9)), f"BBPS/DR/{ref()}/BESCOM ELECTRICITY BILL", rupees(780, 1_420, 10),
        "debit", "expense", "Bills & Utilities")

    # ---- subscriptions / recurring (slightly drifting dates, some amount changes)
    add(day(5 + rng.randint(-1, 1)), f"ACH/DR/{ref()}/NETFLIX.COM", 649_00, "debit", "expense", "Subscriptions")
    add(day(12 + rng.randint(-1, 1)), upi_dr("SPOTIFY INDIA", "spotify@hdfcbank"), 119_00,
        "debit", "expense", "Subscriptions")
    add(day(15), upi_dr("AIRTEL POSTPAID", "airtel@icici", "ICIC"), (599_00 if i < 3 else 649_00),
        "debit", "expense", "Bills & Utilities")
    add(day(10 + rng.randint(0, 2)), f"POS/XXXX9012/CULTFIT GYM MEMBERSHIP", 1_499_00,
        "debit", "expense", "Healthcare")
    if i >= 2:
        add(day(20), upi_dr("JIOHOTSTAR", "jiohotstar@axl", "UTIB"), 299_00, "debit", "expense", "Subscriptions")

    # ---- food delivery (August gets noticeably more)
    food_orders = rng.randint(7, 10) + (8 if i == 4 else 0)
    for _ in range(food_orders):
        merchant = rng.choice([("ZOMATO", "zomato@ybl"), ("SWIGGY", "swiggy@icici")])
        add(day(rng.randint(1, dim)), upi_dr(f"{merchant[0]}*ORDER{rng.randint(1000, 9999)}", merchant[1]),
            rupees(180, 650, 5), "debit", "expense", "Food & Dining")
    for _ in range(rng.randint(2, 4)):
        add(day(rng.randint(1, dim)), f"POS/XXXX9012/TATA STARBUCKS INDIRANAGAR", rupees(250, 520, 5),
            "debit", "expense", "Food & Dining")

    # ---- groceries
    for _ in range(rng.randint(5, 7)):
        name, handle = rng.choice([("BLINKIT", "blinkit@hdfcbank"), ("ZEPTO", "zepto@ybl"),
                                   ("BIGBASKET", "bigbasket@icici"), ("SWIGGY INSTAMART", "instamart@icici")])
        add(day(rng.randint(1, dim)), upi_dr(name, handle), rupees(350, 1_800, 5),
            "debit", "expense", "Groceries")

    # ---- transport
    for _ in range(rng.randint(8, 12)):
        name, handle = rng.choice([("UBER INDIA", "uber@axisbank"), ("OLA CABS", "olacabs@ybl"),
                                   ("RAPIDO", "rapido@ybl"), ("NAMMA METRO BMRCL", "bmrcl@sbi")])
        add(day(rng.randint(1, dim)), upi_dr(name, handle), rupees(45, 420, 5),
            "debit", "expense", "Transport")

    # ---- shopping
    for _ in range(rng.randint(1, 3)):
        name = rng.choice(["AMZN MKTPLACE", "MYNTRA DESIGNS", "FLIPKART INTERNET", "DECATHLON SPORTS"])
        add(day(rng.randint(1, dim)), f"POS/XXXX9012/{name}", rupees(499, 3_999, 1),
            "debit", "expense", "Shopping")

    # ---- uncategorized local merchants and people
    for _ in range(rng.randint(2, 4)):
        name, handle = rng.choice([("SHARMA GENERAL STORE", "sharmastore@okaxis"),
                                   ("SRI SAI TIFFINS", "saitiffins@okicici"),
                                   ("GREEN LEAF SALON", "greenleaf@okhdfcbank")])
        add(day(rng.randint(1, dim)), upi_dr(name, handle, "SBIN"), rupees(60, 900, 5),
            "debit", "expense", "Other")
    add(day(rng.randint(1, dim)), upi_cr("ROHAN MEHTA", "rohan.m@okaxis"), rupees(300, 1_500, 50),
        "credit", "other", "Other")

    # ---- miscellaneous
    add(day(rng.randint(20, 26)), f"ATM WDL/XXXX9012/MG ROAD BRANCH", rupees(1_000, 3_000, 500),
        "debit", "expense", "Other")
    if i in (1, 4):
        add(day(rng.randint(5, 25)), upi_dr("BOOKMYSHOW", "bookmyshow@hdfcbank"), rupees(450, 1_200, 10),
            "debit", "expense", "Entertainment")
    if i in (0, 3):
        add(day(rng.randint(5, 25)), upi_dr("APOLLO PHARMACY", "apollo@icici"), rupees(240, 1_100, 10),
            "debit", "expense", "Healthcare")
    if i == 2:
        add(day(14), f"POS/XXXX9012/INDIGO AIRLINES", 5_890_00, "debit", "expense", "Travel")
        add(day(15), upi_dr("IRCTC WEB", "irctc@sbi", "SBIN"), 1_245_00, "debit", "expense", "Travel")
    if i == 1:
        add(day(22), f"POS/XXXX9012/UDEMY ONLINE COURSES", 499_00, "debit", "expense", "Education")
    if i in (2, 5):
        add(day(30), f"SB INT CREDIT/QTR ENDING", rupees(180, 320, 1), "credit", "income", "Income")

# ---- one-off events that make the demo interesting
aug = month_start(4)
add(aug + timedelta(days=9), f"POS/XXXX9012/AMZN MKTPLACE LAPTOP", 54_999_00, "debit", "expense", "Shopping")
jul = month_start(3)
add(jul + timedelta(days=6), f"POS/XXXX9012/AMZN MKTPLACE", 1_299_00, "debit", "expense", "Shopping")
add(jul + timedelta(days=12), upi_cr("AMAZON REFUND", "amazon@apl", "UTIB"), 1_299_00, "credit", "refund", "Refunds")
add(month_start(5) + timedelta(days=3), f"IMPS/CR/{ref()}/SWEEP IN FROM OWN A/C XXXXXX4521", 15_000_00,
    "credit", "transfer", "Transfers")
# Two genuine identical tea payments on the same day (a "possible duplicate" that is legitimate).
chai_day = month_start(4) + timedelta(days=16)
add(chai_day, "UPI/DR/600000099001/CHAI POINT KORAMANGALA/YESB/chaipoint@ybl/Payment", 120_00,
    "debit", "expense", "Other")
add(chai_day, "UPI/DR/600000099002/CHAI POINT KORAMANGALA/YESB/chaipoint@ybl/Payment", 120_00,
    "debit", "expense", "Other")

events.sort(key=lambda e: (e["date"], e["direction"] == "debit"))

rows = []
balance = OPENING_BALANCE
for e in events:
    balance += e["amount"] if e["direction"] == "credit" else -e["amount"]
    rows.append({
        "date": e["date"].isoformat(),
        "description": e["description"],
        "debit": f"{e['amount'] / 100:.2f}" if e["direction"] == "debit" else "",
        "credit": f"{e['amount'] / 100:.2f}" if e["direction"] == "credit" else "",
        "balance": f"{balance / 100:.2f}",
        "truth_type": e["truth_type"],
        "truth_category": e["truth_category"],
    })
    assert balance > 0, "synthetic balance went negative"

# An exact duplicate row, as happens when a PDF page break repeats a line.
dup_index = next(i for i, r in enumerate(rows) if "BLINKIT" in r["description"] and r["date"] >= "2026-06-01")
dup = dict(rows[dup_index])
dup["truth_type"] = "duplicate"
rows.insert(dup_index + 1, dup)

OUT.parent.mkdir(parents=True, exist_ok=True)
with open(OUT, "w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)

print(f"Wrote {len(rows)} synthetic transactions to {OUT}")
