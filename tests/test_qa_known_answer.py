"""QA: a known-answer synthetic account, checked against hand-calculated values.

Every expected number below was worked out by hand from the rows in KNOWN (rules
from README "Financial metric definitions"):

  expenditure  = debits classified as spending (transfers and card-bill payments excluded), before refunds
  income       = credits classified as income (salary). A friend's transfer is "other", not income.
  refunds      = credits classified as refunds; never income, never subtracted from categories
  net cash flow= all credits − all debits, excluding transfers between own accounts
                 (the card-bill payment counts: that money left the account)

Statement 1 covers 2026-01-01 → 2026-03-31 (March has no rows: a real zero).
Statement 2 covers 2026-04-01 → 2026-04-10 (partial month).

                         Jan        Feb       Mar   Apr 1–10
  expenditure         19,639     76,249        0        949
  income              50,000     50,000        0     50,000
  refunds                500          0        0          0
  net cash flow      +28,861    −26,249        0    +49,051
"""

import random
from datetime import date

import pandas as pd
import pytest

from src import analytics, anomaly_detector, database, insights, kpis, pipeline, subscription_detector
from src.analytics import Filters
from tests.conftest import rows_to_csv
from tests.test_advanced_analytics import make_conn

KNOWN = [
    # date,        description,                                 debit,      credit
    ("2026-01-01", "NEFT/CR/100001/ACME TECH/SALARY JAN",        None,       "50000.00"),
    ("2026-01-03", "IMPS/DR/100002/HOUSE RENT/MR K NAIR",        "15000.00", None),
    ("2026-01-05", "UPI/DR/100003/ZOMATO/YESB/zomato@ybl",       "400.00",   None),
    ("2026-01-10", "ACH/DR/100004/NETFLIX.COM",                  "649.00",   None),
    ("2026-01-12", "UPI/DR/100005/IRCTC/YESB",                   "1200.00",  None),
    ("2026-01-15", "POS/XXXX1111/AMZN MKTPLACE",                 "2000.00",  None),
    ("2026-01-18", "UPI/CR/100006/AMAZON REFUND/UTIB",           None,       "500.00"),
    ("2026-01-20", "IMPS/DR/100007/SELF TRANSFER TO OWN A/C",    "10000.00", None),
    ("2026-01-22", "BILLDESK/CREDIT CARD PAYMENT/HDFC CARD",     "3000.00",  None),
    ("2026-01-25", "UPI/CR/100008/ROHAN MEHTA/HDFC/rohan@okaxis", None,      "1000.00"),
    ("2026-01-28", "UPI/DR/100009/CHAI POINT/YESB",              "20.00",    None),
    ("2026-01-28", "UPI/DR/100009/CHAI POINT/YESB",              "20.00",    None),   # possible duplicate
    ("2026-01-30", "UPI/DR/100010/SHARMA STORES/YESB",           "350.00",   None),   # no rule → Other
    ("2026-02-01", "NEFT/CR/100011/ACME TECH/SALARY FEB",        None,       "50000.00"),
    ("2026-02-03", "IMPS/DR/100012/HOUSE RENT/MR K NAIR",        "15000.00", None),
    ("2026-02-07", "UPI/DR/100013/ZOMATO/YESB/zomato@ybl",       "600.00",   None),
    ("2026-02-10", "ACH/DR/100014/NETFLIX.COM",                  "649.00",   None),
    ("2026-02-14", "POS/XXXX1111/AMZN MKTPLACE",                 "60000.00", None),   # unusually large
    ("2026-04-01", "NEFT/CR/100015/ACME TECH/SALARY APR",        None,       "50000.00"),
    ("2026-04-05", "UPI/DR/100016/ZOMATO/YESB/zomato@ybl",       "300.00",   None),
    ("2026-04-10", "ACH/DR/100017/NETFLIX.COM",                  "649.00",   None),
]
PERIODS = [("2026-01-01", "2026-03-31"), ("2026-04-01", "2026-04-10")]
R = 100  # paise per rupee


@pytest.fixture(scope="module")
def conn():
    return make_conn(KNOWN, PERIODS)


def _month(conn, m):
    start = date.fromisoformat(f"{m}-01")
    end = (pd.Timestamp(start) + pd.offsets.MonthEnd(0)).date()
    return analytics.totals(conn, Filters(start_date=start, end_date=end))


def test_all_rows_imported(conn):
    assert database.count_transactions(conn) == len(KNOWN)   # possible duplicate kept, flagged


def test_totals(conn):
    t = analytics.totals(conn)
    assert t["expenditure_paise"] == 96_837 * R
    assert t["income_paise"] == 150_000 * R
    assert t["refunds_paise"] == 500 * R
    assert t["net_cash_flow_paise"] == 51_663 * R
    assert t["transfers_paise"] == 10_000 * R and t["cc_repayments_paise"] == 3_000 * R


@pytest.mark.parametrize("month,exp,inc,ref,net", [
    ("2026-01", 19_639, 50_000, 500, 28_861),
    ("2026-02", 76_249, 50_000, 0, -26_249),
    ("2026-03", 0, 0, 0, 0),
    ("2026-04", 949, 50_000, 0, 49_051),
])
def test_per_month(conn, month, exp, inc, ref, net):
    t = _month(conn, month)
    assert (t["expenditure_paise"], t["income_paise"], t["refunds_paise"], t["net_cash_flow_paise"]) == \
           (exp * R, inc * R, ref * R, net * R)


def test_exclusions_and_friend_transfer(conn):
    tx = analytics.transactions(conn)
    by_desc = {r.description: r for r in tx.itertuples()}
    assert by_desc["IMPS/DR/100007/SELF TRANSFER TO OWN A/C"].transaction_type == "transfer"
    assert by_desc["BILLDESK/CREDIT CARD PAYMENT/HDFC CARD"].transaction_type == "cc_repayment"
    friend = next(r for r in tx.itertuples() if r.normalized_merchant == "Rohan Mehta")
    assert friend.transaction_type == "other" and "[upi-id]" in friend.description   # masked, not income
    refund = next(r for r in tx.itertuples() if r.transaction_type == "refund")
    assert refund.category == "Refunds"


def test_categories(conn):
    cats = analytics.category_spending(conn).set_index("category")["expenditure_paise"].to_dict()
    assert cats == {"Shopping": 62_000 * R, "Rent & Housing": 30_000 * R, "Subscriptions": 1_947 * R,
                    "Food & Dining": 1_300 * R, "Travel": 1_200 * R, "Other": 390 * R}
    assert sum(cats.values()) == analytics.totals(conn)["expenditure_paise"]


def test_monthly_summary_distinguishes_zero_from_missing(conn):
    m = analytics.monthly_summary(conn).set_index("month_start")
    assert int(m.loc["2026-03-01", "is_covered"]) == 1 and int(m.loc["2026-03-01", "expenditure_paise"]) == 0
    assert m.loc["2026-03-01", "mom_change_pct"] == -100.0                 # 76,249 → 0, both covered
    assert pd.isna(m.loc["2026-04-01", "mom_change_pct"])                  # previous month had no spending
    assert int(m.loc["2026-04-01", "is_full_month"]) == 0                  # partial


def test_month_over_month_partial_and_zero_previous(conn):
    comp = insights.compare_periods(conn)
    assert comp.is_partial and comp.current == (date(2026, 4, 1), date(2026, 4, 10))
    assert comp.previous == (date(2026, 3, 1), date(2026, 3, 10))
    assert (comp.current_paise, comp.previous_paise, comp.change_pct) == (949 * R, 0, None)
    assert "isn't meaningful" in insights.describe_change(comp).text
    feb = insights.compare_periods(conn, Filters(end_date=date(2026, 2, 28)))
    assert feb.change_pct == round(100 * (76_249 - 19_639) / 19_639, 1)


def test_executive_average_uses_complete_months(conn):
    s = kpis.executive_summary(conn)
    # Jan, Feb and Mar are complete (Mar is a real zero); April is partial.
    assert s["average_monthly_expenditure"] == {"value_paise": round((19_639 + 76_249 + 0) * R / 3), "months": 3}


def test_possible_duplicate_flagged_not_merged(conn):
    tx = analytics.transactions(conn, Filters(statuses=("possible_duplicate",)))
    assert list(tx["normalized_merchant"]) == ["Chai Point"]
    assert analytics.totals(conn)["possible_duplicate_count"] == 1


def test_uncategorised(conn):
    tx = analytics.transactions(conn, Filters(statuses=("uncategorized",)))
    assert set(tx["normalized_merchant"]) == {"Chai Point", "Sharma Stores", "Rohan Mehta"}


def test_recurring_is_conservative(conn):
    cands = {c.merchant: c for c in subscription_detector.detect_for(conn)}
    # Netflix: Jan 10, Feb 10, Apr 10 — the March payment is missing, so the gaps aren't all monthly.
    # The detector must not claim a confident subscription from this evidence.
    assert "Netflix" not in cands or cands["Netflix"].status not in {"high_confidence", "confirmed"}
    # Rent has only two payments: below the minimum, so it isn't claimed as recurring at all.
    assert "House Rent" not in cands


def test_large_purchase_without_history_is_not_flagged(conn):
    flagged, info = anomaly_detector.detect_anomalies(analytics.transactions(conn))
    assert flagged.empty
    assert info["insufficient_history"] == info["checked"] + info["insufficient_history"]  # nothing checkable


# ------------------------------------------------------------- invariants

def test_reordering_rows_does_not_change_totals():
    base = analytics.totals(make_conn(KNOWN, PERIODS))
    for seed in range(5):
        rows = KNOWN[:]
        random.Random(seed).shuffle(rows)
        t = analytics.totals(make_conn(rows, PERIODS))
        for key in ("expenditure_paise", "income_paise", "refunds_paise", "net_cash_flow_paise"):
            assert t[key] == base[key]


def test_aggregation_is_deterministic(conn):
    a = analytics.category_spending(conn)
    b = analytics.category_spending(conn)
    pd.testing.assert_frame_equal(a, b)
    assert list(analytics.top_merchants(conn, limit=10)["merchant"]) == list(analytics.top_merchants(conn, limit=10)["merchant"])


def test_same_file_twice_is_blocked():
    c = database.connect(":memory:")
    text = rows_to_csv(KNOWN)
    pipeline.commit_import(c, pipeline.prepare_csv_rows_import(text, display_name="a", conn=c))
    again = pipeline.prepare_csv_rows_import(text, display_name="a", conn=c)
    assert again.already_imported
    with pytest.raises(ValueError):
        pipeline.commit_import(c, again)
    assert database.count_transactions(c) == len(KNOWN)


def test_overlapping_statement_without_balances_is_flagged_not_silent():
    """Same rows in a different file and no balance/ID: they can't be proven copies, so they are
    imported but EVERY one is flagged as a possible duplicate (documented rule)."""
    c = database.connect(":memory:")
    pipeline.commit_import(c, pipeline.prepare_csv_rows_import(rows_to_csv(KNOWN), display_name="a", conn=c))
    second = pipeline.prepare_csv_rows_import(rows_to_csv(KNOWN) + "\n", display_name="b", conn=c)
    assert all(r["duplicate_status"] == "possible" for r in second.rows)


def test_overlapping_statement_with_balances_is_not_double_counted():
    bal = 1_00_000_00
    lines = ["date,description,debit,credit,balance"]
    for i in range(10):
        bal -= (i + 1) * 100_00
        lines.append(f"2026-05-{i + 1:02d},UPI/DR/2000{i}/ZOMATO/YESB,{(i + 1) * 100}.00,,{bal / 100:.2f}")
    first, second = "\n".join(lines[:8]) + "\n", "\n".join([lines[0]] + lines[4:]) + "\n"   # rows 4–7 overlap
    c = database.connect(":memory:")
    pipeline.commit_import(c, pipeline.prepare_csv_rows_import(first, display_name="a", conn=c))
    p = pipeline.prepare_csv_rows_import(second, display_name="b", conn=c)
    assert sum(r["duplicate_status"] == "exact_existing" for r in p.rows) == 4
    pipeline.commit_import(c, p)
    assert database.count_transactions(c) == 10
    assert analytics.totals(c)["expenditure_paise"] == sum((i + 1) * 100_00 for i in range(10))


def test_invalid_rows_never_reach_aggregates():
    rows = KNOWN[:3] + [("2026-01-31", "UPI/DR/9/ZOMATO/YESB", "abc", None), ("31/02/2026", "UPI/DR/8/ZOMATO", "99.00", None)]
    c = make_conn(rows, [("2026-01-01", "2026-01-31")])
    assert analytics.totals(c)["expenditure_paise"] == (15_000 + 400) * R
