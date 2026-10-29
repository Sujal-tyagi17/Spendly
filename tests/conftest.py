"""Shared synthetic fixtures. No real bank data is used anywhere in the tests."""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import database, pipeline  # noqa: E402

# A tiny hand-made statement with hand-computed expected results
# (see test_analytics.py for the arithmetic).
SMALL_CSV = """date,description,debit,credit,balance
2026-01-01,NEFT/CR/123456789012/ACME ANALYTICS/SALARY JAN 2026,,50000.00,
2026-01-05,UPI/DR/111111111111/ZOMATO/YESB/zomato@ybl/Payment,500.00,,
2026-01-10,POS/XXXX1111/AMZN MKTPLACE,2000.00,,
2026-01-12,UPI/CR/222222222222/AMAZON REFUND/UTIB/amazon@apl/Payment,,500.00,
2026-01-15,IMPS/DR/333333333333/SELF TRANSFER TO OWN A/C,10000.00,,
2026-01-20,BILLDESK/CREDIT CARD PAYMENT/HDFC CARD,3000.00,,
2026-03-03,UPI/DR/444444444444/ZOMATO/YESB/zomato@ybl/Payment,700.00,,
2026-03-04,UPI/DR/555555555555/UBER INDIA/YESB/uber@axisbank/Payment,300.00,,
2026-03-05,UPI/CR/666666666666/ROHAN MEHTA/HDFC/rohan@okaxis/Payment,,1000.00,
"""


def conn_from_csv(text: str, period=(None, None)):
    conn = database.connect(":memory:")
    preview = pipeline.prepare_csv_rows_import(text, display_name="test", conn=conn, period=period)
    pipeline.commit_import(conn, preview)
    return conn


def rows_to_csv(rows: list[tuple]) -> str:
    """rows: (date, description, debit, credit) tuples -> CSV text."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", "description", "debit", "credit", "balance"])
    for d, desc, debit, credit in rows:
        writer.writerow([d, desc, debit or "", credit or "", ""])
    return buffer.getvalue()


@pytest.fixture
def small_conn():
    conn = conn_from_csv(SMALL_CSV)
    yield conn
    conn.close()


@pytest.fixture
def empty_conn():
    conn = database.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def demo_truth():
    with open(ROOT / "data" / "sample_transactions.csv", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture
def demo_conn():
    conn = database.connect(":memory:")
    pipeline.load_demo_dataset(conn)
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def _fresh_rate_limiter():
    """The API's rate limiter is process-wide; start every test with empty counters."""
    from api import main
    main.limiter.reset()
    yield
