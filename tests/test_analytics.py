"""Analytics tests against hand-computed numbers (SMALL_CSV in conftest.py).

SMALL_CSV, by month (₹):
  Jan: salary +50,000 | Zomato -500 | Amazon -2,000 | Amazon refund +500
       self transfer -10,000 | credit-card bill -3,000
  Feb: nothing (must still appear as a zero month)
  Mar: Zomato -700 | Uber -300 | money from a friend +1,000

  Jan expenditure      = 500 + 2,000            = 2,500
  Jan net expenditure  = 2,500 - 500 refund     = 2,000
  Jan net cash flow    = (50,000 + 500) - (500 + 2,000 + 3,000) = 45,000   (transfer excluded)
  Mar expenditure      = 1,000 ; Mar net cash flow = 1,000 - 1,000 = 0
"""

from datetime import date

import pandas as pd
import pytest

from src import analytics
from src.analytics import FilterError, Filters


def test_monthly_summary_matches_hand_calculation(small_conn):
    m = analytics.monthly_summary(small_conn).set_index("month_start")
    assert list(m.index) == ["2026-01-01", "2026-02-01", "2026-03-01"]  # Feb filled in
    jan, feb, mar = m.loc["2026-01-01"], m.loc["2026-02-01"], m.loc["2026-03-01"]
    assert jan.expenditure_paise == 2_500_00
    assert jan.refunds_paise == 500_00
    assert jan.net_expenditure_paise == 2_000_00
    assert jan.income_paise == 50_000_00
    assert jan.transfers_paise == 10_000_00
    assert jan.cc_repayments_paise == 3_000_00
    assert jan.net_cash_flow_paise == 45_000_00
    assert feb.expenditure_paise == 0 and feb.transaction_count == 0
    assert mar.expenditure_paise == 1_000_00 and mar.net_cash_flow_paise == 0


def test_month_over_month_and_zero_denominator(small_conn):
    m = analytics.monthly_summary(small_conn).set_index("month_start")
    assert pd.isna(m.loc["2026-01-01", "mom_change_pct"])            # no previous month
    assert m.loc["2026-02-01", "mom_change_pct"] == -100.0           # 2,500 -> 0
    assert pd.isna(m.loc["2026-03-01", "mom_change_pct"])            # previous month was 0: no %


def test_totals(small_conn):
    t = analytics.totals(small_conn)
    assert t["expenditure_paise"] == 3_500_00
    assert t["refunds_paise"] == 500_00
    assert t["income_paise"] == 50_000_00                 # the friend's ₹1,000 is NOT income
    assert t["total_credits_paise"] == 51_500_00
    assert t["gross_debits_paise"] == 16_500_00           # every debit, transfers included
    assert t["transfers_paise"] == 10_000_00
    assert t["net_cash_flow_paise"] == 45_000_00
    assert t["uncategorized_count"] == 1


def test_transfers_and_card_repayments_excluded_from_expenditure(small_conn):
    cats = analytics.category_spending(small_conn)
    assert "Transfers" not in set(cats["category"])
    assert cats["expenditure_paise"].sum() == 3_500_00


def test_category_spending_shares(small_conn):
    cats = analytics.category_spending(small_conn).set_index("category")
    assert cats.loc["Shopping", "expenditure_paise"] == 2_000_00
    assert cats.loc["Food & Dining", "expenditure_paise"] == 1_200_00
    assert cats.loc["Food & Dining", "avg_transaction_paise"] == 600_00
    assert cats.loc["Shopping", "share_pct"] == 57.1
    assert cats.loc["Shopping", "spend_rank"] == 1
    assert round(cats["share_pct"].sum()) == 100


def test_top_merchants_and_largest(small_conn):
    top = analytics.top_merchants(small_conn, limit=2)
    assert list(top["merchant"]) == ["Amazon", "Zomato"]
    assert top.iloc[1]["expenditure_paise"] == 1_200_00
    largest = analytics.largest_transactions(small_conn, limit=1)
    assert largest.iloc[0]["amount_paise"] == 2_000_00


def test_weekday_spending(small_conn):
    w = analytics.weekday_spending(small_conn).set_index("weekday_name")
    assert len(w) == 7                                   # every weekday present
    assert w.loc["Monday", "expenditure_paise"] == 500_00      # 5 Jan 2026
    assert w.loc["Saturday", "expenditure_paise"] == 2_000_00  # 10 Jan 2026
    assert w.loc["Tuesday", "expenditure_paise"] == 700_00     # 3 Mar 2026
    assert w.loc["Friday", "expenditure_paise"] == 0


def test_filters_apply_consistently(small_conn):
    jan = Filters(start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
    assert analytics.totals(small_conn, jan)["expenditure_paise"] == 2_500_00
    food = Filters(categories=("Food & Dining",))
    assert analytics.totals(small_conn, food)["expenditure_paise"] == 1_200_00
    assert analytics.category_spending(small_conn, food)["expenditure_paise"].sum() == 1_200_00
    uber = Filters(merchants=("Uber",))
    assert analytics.totals(small_conn, uber)["expenditure_paise"] == 300_00
    refunds_only = Filters(transaction_types=("refund",))
    assert analytics.totals(small_conn, refunds_only)["refunds_paise"] == 500_00
    assert analytics.totals(small_conn, refunds_only)["expenditure_paise"] == 0


def test_invalid_date_range_raises(small_conn):
    with pytest.raises(FilterError):
        analytics.totals(small_conn, Filters(start_date=date(2026, 3, 1), end_date=date(2026, 1, 1)))


def test_period_change(small_conn):
    change = analytics.period_change(small_conn, "category_change", Filters(),
                                     (date(2026, 3, 1), date(2026, 3, 31)), (date(2026, 1, 1), date(2026, 1, 31)))
    c = change.set_index("category")
    assert c.loc["Shopping", "change_paise"] == -2_000_00
    assert c.loc["Transport", "previous_paise"] == 0 and pd.isna(c.loc["Transport", "change_pct"])
    assert c.loc["Food & Dining", "change_pct"] == 40.0   # 500 -> 700


def test_empty_database_is_safe(empty_conn):
    t = analytics.totals(empty_conn)
    assert t["transaction_count"] == 0 and t["expenditure_paise"] == 0
    assert analytics.monthly_summary(empty_conn).empty
    assert analytics.category_spending(empty_conn).empty
    assert len(analytics.weekday_spending(empty_conn)) == 7
    assert analytics.date_bounds(empty_conn) == (None, None)


def test_demo_totals_match_independent_pandas_calculation(demo_conn, demo_truth):
    """Recompute the headline numbers from the raw CSV with pandas and compare with SQL."""
    df = pd.DataFrame([t for t in demo_truth if t["truth_type"] != "duplicate"])
    df["debit_paise"] = (pd.to_numeric(df["debit"], errors="coerce").fillna(0) * 100).round().astype(int)
    df["credit_paise"] = (pd.to_numeric(df["credit"], errors="coerce").fillna(0) * 100).round().astype(int)
    expense = df.loc[df.truth_type == "expense", "debit_paise"].sum()
    refunds = df.loc[df.truth_type == "refund", "credit_paise"].sum()
    income = df.loc[df.truth_type == "income", "credit_paise"].sum()
    non_transfer = df[df.truth_type != "transfer"]
    net_cash = non_transfer["credit_paise"].sum() - non_transfer["debit_paise"].sum()

    t = analytics.totals(demo_conn)
    assert t["expenditure_paise"] == expense
    assert t["refunds_paise"] == refunds
    assert t["income_paise"] == income
    assert t["net_cash_flow_paise"] == net_cash
    monthly = analytics.monthly_summary(demo_conn)
    assert monthly["expenditure_paise"].sum() == expense
    assert len(monthly) == 6


def test_sql_filter_values_are_parameterized(small_conn):
    evil = Filters(search="'; DROP TABLE transactions; --", categories=("x') OR 1=1 --",))
    assert analytics.transactions(small_conn, evil).empty
    assert analytics.totals(small_conn)["transaction_count"] == 9  # table still intact


def test_status_filters_sorting_and_paging(demo_conn):
    dup = analytics.transactions(demo_conn, Filters(statuses=("possible_duplicate",)))
    assert len(dup) == 1 and dup.iloc[0]["normalized_merchant"] == "Chai Point Koramangala"
    assert analytics.count_transactions(demo_conn, Filters(statuses=("uncategorized",))) == 24
    biggest = analytics.transactions(demo_conn, sort="amount", descending=True, limit=1)
    assert biggest.iloc[0]["transaction_type"] == "income"  # largest money-in first
    page2 = analytics.transactions(demo_conn, limit=10, offset=10)
    assert len(page2) == 10
    with pytest.raises(FilterError):
        analytics.transactions(demo_conn, sort="amount_paise; DROP TABLE transactions")
    with pytest.raises(FilterError):
        analytics.count_transactions(demo_conn, Filters(statuses=("bogus",)))
