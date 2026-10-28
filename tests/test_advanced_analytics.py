"""Advanced SQL analytics, checked against values computed by hand / plain Python.

The expectations are NOT produced by the SQL under test: they are written out
by hand below (or recomputed with ordinary Python from the raw fixture rows),
so a wrong formula in SQL cannot "agree with itself".

Fixture (rupees). 2026-01-03 is a Saturday.
  Jan  Sat 03  Zomato         300
       Sun 04  Zomato         500
       Mon 05  Amazon        1000
       Tue 06  Uber           200
       Wed 07  self transfer 5000   (transfer — never spending)
       Thu 08  Amazon refund  400 cr
       Sat 10  salary       30000 cr
       Mon 12  card bill     3000   (cc repayment — not spending)
  Feb  (nothing)
  Mar  Mon 02  Zomato         700
       Sat 07  Amazon        2500
       Sun 08  Netflix        649
"""

from datetime import date, timedelta
from statistics import median

import pandas as pd
import pytest

from src import analytics, database, metrics, pipeline, subscription_detector
from src.analytics import Filters
from tests.conftest import rows_to_csv

ROWS = [
    ("2026-01-03", "UPI/DR/1/ZOMATO/YESB", "300.00", None),
    ("2026-01-04", "UPI/DR/2/ZOMATO/YESB", "500.00", None),
    ("2026-01-05", "POS/XXXX1111/AMZN MKTPLACE", "1000.00", None),
    ("2026-01-06", "UPI/DR/3/UBER INDIA/YESB", "200.00", None),
    ("2026-01-07", "IMPS/DR/4/SELF TRANSFER TO OWN A/C", "5000.00", None),
    ("2026-01-08", "UPI/CR/5/AMAZON REFUND/UTIB", None, "400.00"),
    ("2026-01-10", "NEFT/CR/6/ACME/SALARY JAN", None, "30000.00"),
    ("2026-01-12", "BILLDESK/CREDIT CARD PAYMENT", "3000.00", None),
    ("2026-03-02", "UPI/DR/7/ZOMATO/YESB", "700.00", None),
    ("2026-03-07", "POS/XXXX1111/AMZN MKTPLACE", "2500.00", None),
    ("2026-03-08", "ACH/DR/8/NETFLIX.COM", "649.00", None),
]

# Independent expectations (paise)
SPEND = {  # merchant -> list of expense payments
    "Zomato": [300_00, 500_00, 700_00],
    "Amazon": [1000_00, 2500_00],
    "Uber": [200_00],
    "Netflix": [649_00],
}
TOTAL = sum(sum(v) for v in SPEND.values())  # 5,849
JAN, MAR = 2000_00, 3849_00


def make_conn(rows, periods):
    """Import rows split into statements with explicit coverage periods."""
    conn = database.connect(":memory:")
    for start, end in periods:
        chunk = [r for r in rows if start <= r[0] <= end]
        preview = pipeline.prepare_csv_rows_import(rows_to_csv(chunk), display_name=f"{start}", conn=conn,
                                                   period=(start, end))
        pipeline.commit_import(conn, preview)
    return conn


@pytest.fixture
def one_statement():
    """Jan–Mar covered by one statement → February is a genuine zero month."""
    return make_conn(ROWS, [("2026-01-01", "2026-03-31")])


@pytest.fixture
def gap():
    """Separate Jan and Mar statements → February is MISSING data, not zero."""
    return make_conn(ROWS, [("2026-01-01", "2026-01-31"), ("2026-03-01", "2026-03-31")])


# ------------------------------------------------------------ month over month

def test_monthly_values_and_genuine_zero_month(one_statement):
    m = analytics.monthly_summary(one_statement).set_index("month_start")
    assert m.loc["2026-01-01", "expenditure_paise"] == JAN
    assert m.loc["2026-02-01", "expenditure_paise"] == 0
    assert m.loc["2026-03-01", "expenditure_paise"] == MAR
    assert list(m["is_covered"]) == [1, 1, 1]
    assert list(m["prev_status"]) == ["none", "value", "zero"]
    assert m.loc["2026-02-01", "expenditure_change_paise"] == -JAN
    assert m.loc["2026-02-01", "mom_change_pct"] == -100.0
    assert m.loc["2026-03-01", "expenditure_change_paise"] == MAR      # from a real zero
    assert pd.isna(m.loc["2026-03-01", "mom_change_pct"])             # no % from zero


def test_missing_month_is_not_treated_as_zero(gap):
    m = analytics.monthly_summary(gap).set_index("month_start")
    assert m.loc["2026-02-01", "is_covered"] == 0
    assert m.loc["2026-03-01", "prev_status"] == "not_covered"
    assert pd.isna(m.loc["2026-03-01", "expenditure_change_paise"])
    assert pd.isna(m.loc["2026-03-01", "mom_change_pct"])
    assert pd.isna(m.loc["2026-02-01", "expenditure_change_paise"])  # an uncovered month has no change


def test_partial_month_flag():
    conn = make_conn(ROWS, [("2026-01-01", "2026-03-08")])
    m = analytics.monthly_summary(conn).set_index("month_start")
    assert m.loc["2026-01-01", "is_full_month"] == 1
    assert m.loc["2026-03-01", "is_full_month"] == 0


# ------------------------------------------------------------------ cash flow

def test_cash_flow_excludes_transfers_includes_card_bill(one_statement):
    m = analytics.monthly_summary(one_statement).set_index("month_start")
    # Jan: credits 30,400 − debits (300+500+1000+200+3000) = 25,400; transfer excluded
    assert m.loc["2026-01-01", "net_cash_flow_paise"] == 25_400_00
    assert m.loc["2026-01-01", "income_paise"] == 30_000_00
    assert m.loc["2026-01-01", "refunds_paise"] == 400_00
    assert m.loc["2026-01-01", "transfers_paise"] == 5_000_00
    assert m.loc["2026-01-01", "cc_repayments_paise"] == 3_000_00
    # running total: 25,400 → 25,400 → 25,400 − 3,849
    assert list(m["cumulative_net_cash_flow_paise"]) == [25_400_00, 25_400_00, 25_400_00 - 3_849_00]


# ------------------------------------------------------------------ categories

def test_category_monthly_grid_and_change(one_statement):
    g = analytics.monthly_category(one_statement)
    food = g[g.category == "Food & Dining"].set_index("month_start")
    assert list(food["expenditure_paise"]) == [800_00, 0, 700_00]        # Feb filled with 0
    assert food.loc["2026-03-01", "change_paise"] == 700_00
    assert pd.isna(food.loc["2026-01-01", "prev_expenditure_paise"])
    jan = g[g.month_start == "2026-01-01"].set_index("category")
    assert jan.loc["Shopping", "rank_in_month"] == 1 and jan.loc["Food & Dining", "rank_in_month"] == 2
    assert jan.loc["Shopping", "share_of_month_pct"] == 50.0             # 1000 / 2000
    feb = g[g.month_start == "2026-02-01"].set_index("category")
    # Feb change −2000: Shopping −1000 (50%), Food −800 (40%), Transport −200 (10%)
    assert feb.loc["Shopping", "share_of_change_pct"] == 50.0
    assert feb.loc["Food & Dining", "share_of_change_pct"] == 40.0


def test_transfers_and_refunds_never_appear_as_spending_categories(one_statement):
    g = analytics.monthly_category(one_statement)
    assert not {"Transfers", "Refunds", "Income"} & set(g["category"])
    assert g["expenditure_paise"].sum() == TOTAL


# ------------------------------------------------------------------- merchants

def test_merchant_stats_against_python(one_statement):
    s = analytics.merchant_stats(one_statement).set_index("merchant")
    for merchant, amounts in SPEND.items():
        row = s.loc[merchant]
        assert row["expenditure_paise"] == sum(amounts)
        assert row["transaction_count"] == len(amounts)
        assert row["avg_transaction_paise"] == round(sum(amounts) / len(amounts))
        assert row["median_transaction_paise"] == round(median(amounts))
        assert row["share_pct"] == round(100 * sum(amounts) / TOTAL, 2)
    assert list(s.index) == ["Amazon", "Zomato", "Netflix", "Uber"]
    assert s.loc["Amazon", "spend_rank"] == 1 and s.loc["Zomato", "frequency_rank"] == 1
    assert s["cumulative_share_pct"].iloc[-1] == 100.0
    assert s.loc["Zomato", "active_months"] == 2


def test_median_even_and_odd():
    rows = [(f"2026-05-{d:02d}", f"UPI/DR/{d}/ZOMATO/YESB", f"{a}.00", None)
            for d, a in [(1, 100), (2, 400), (3, 200), (4, 900)]]
    conn = make_conn(rows, [("2026-05-01", "2026-05-31")])
    assert analytics.merchant_stats(conn).iloc[0]["median_transaction_paise"] == 300_00  # (200+400)/2


# --------------------------------------------------------------- concentration

def test_concentration_against_python(one_statement):
    c = analytics.concentration(one_statement)
    shares = sorted((100 * sum(v) / TOTAL for v in SPEND.values()), reverse=True)
    assert c["merchant_count"] == 4
    assert c["top_1_share_pct"] == round(shares[0], 2)
    assert c["top_5_share_pct"] == 100.0 and c["top_10_share_pct"] == 100.0
    assert c["hhi"] == round(sum(s * s for s in shares), 1)
    assert c["top_merchant"] == "Amazon" and c["top_category"] == "Shopping"


def test_concentration_empty(empty_conn):
    c = analytics.concentration(empty_conn)
    assert c["merchant_count"] == 0 and c["top_5_share_pct"] is None and c["hhi"] is None


# ------------------------------------------------------------ weekday / weekend

def test_weekend_split_against_python(one_statement):
    w = analytics.weekend_split(one_statement).set_index("scope")
    all_ = w.loc["All categories"]
    weekend = 300_00 + 500_00 + 2500_00 + 649_00          # Jan 3, 4; Mar 7, 8
    weekday = 1000_00 + 200_00 + 700_00
    assert (all_["weekend_paise"], all_["weekday_paise"]) == (weekend, weekday)
    assert (all_["weekend_txns"], all_["weekday_txns"]) == (4, 3)
    # calendar days in the data span 3 Jan – 8 Mar, counted with plain Python
    days = [date(2026, 1, 3) + timedelta(i) for i in range((date(2026, 3, 8) - date(2026, 1, 3)).days + 1)]
    wk_end = sum(d.weekday() >= 5 for d in days)
    assert (all_["weekend_days"], all_["weekday_days"]) == (wk_end, len(days) - wk_end)
    assert all_["weekend_per_day_paise"] == round(weekend / wk_end)
    food = w.loc["Food & Dining"]
    assert (food["weekend_paise"], food["weekday_paise"]) == (800_00, 700_00)


def test_weekend_split_respects_date_filter(one_statement):
    w = analytics.weekend_split(one_statement, Filters(start_date=date(2026, 3, 1), end_date=date(2026, 3, 31)))
    all_ = w.set_index("scope").loc["All categories"]
    assert all_["weekday_days"] + all_["weekend_days"] == 31
    assert all_["weekend_paise"] == 2500_00 + 649_00


def test_weekend_split_empty(empty_conn):
    w = analytics.weekend_split(empty_conn)
    assert len(w) == 1 and w.iloc[0]["weekday_paise"] == 0


# ------------------------------------------------------------------- recurring

def test_recurring_share_uses_actual_payments_once(demo_conn):
    candidates = subscription_detector.detect_recurring(analytics.recurring_candidates(demo_conn))
    r = subscription_detector.recurring_spend(demo_conn, Filters(), candidates)
    # Independent: sum the raw expense rows of those merchants straight from the table.
    placeholders = ",".join("?" * len(r["merchants"]))
    expected = demo_conn.execute(
        f"SELECT SUM(amount_paise) FROM transactions WHERE transaction_type='expense' AND direction='debit' "
        f"AND normalized_merchant IN ({placeholders})", r["merchants"]).fetchone()[0]
    assert r["actual_recurring_paise"] == expected
    assert r["share_of_expenditure_pct"] == round(100 * expected / r["total_expenditure_paise"], 1)
    assert sum(m["recurring_paise"] for m in r["monthly"]) == expected
    assert r["estimated_annual_paise"] == r["estimated_monthly_paise"] * 12
    assert "Own account transfer" not in r["merchants"]


# ----------------------------------------------------- shared metric definitions

def test_every_sql_file_renders_and_uses_shared_definitions():
    from src import config
    for path in config.SQL_DIR.glob("*.sql"):
        text = path.read_text()
        rendered = metrics.render(text)
        assert "{{" not in rendered, path.name
        # The raw expense predicate must not be hand-written anywhere any more.
        assert "transaction_type = 'expense' AND direction = 'debit'" not in text, path.name


def test_unknown_placeholder_is_an_error():
    with pytest.raises(metrics.UnknownMetricError):
        metrics.render("SELECT {{is_magic}}")


def test_zero_and_negative_amounts_are_rejected_at_import():
    rows = [("2026-01-01", "ZOMATO", "0.00", None), ("2026-01-02", "ZOMATO", "-50.00", None)]
    preview = pipeline.prepare_csv_rows_import(rows_to_csv(rows), display_name="x", conn=None)
    # "0.00" is treated as an empty cell; a negative debit is not a valid amount for that column.
    assert len(preview.rows) == 0 and len(preview.invalid_rows) == 2


def test_duplicate_rows_are_not_double_counted():
    conn = database.connect(":memory:")
    text = "date,description,debit,credit,balance\n2026-01-03,UPI/DR/1/ZOMATO/YESB,300.00,,9700.00\n" \
           "2026-01-03,UPI/DR/1/ZOMATO/YESB,300.00,,9700.00\n"
    preview = pipeline.prepare_csv_rows_import(text, display_name="d", conn=conn)
    pipeline.commit_import(conn, preview)
    assert analytics.totals(conn)["expenditure_paise"] == 300_00
    assert analytics.merchant_stats(conn).iloc[0]["transaction_count"] == 1
