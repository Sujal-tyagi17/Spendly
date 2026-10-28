from datetime import date

from src import analytics, insights
from src.analytics import Filters
from src.insights import comparison_periods, compare_periods, describe_change
from tests.conftest import conn_from_csv, rows_to_csv


def test_complete_month_compares_with_full_previous_month():
    cur, prev, partial = comparison_periods(date(2026, 3, 31))
    assert cur == (date(2026, 3, 1), date(2026, 3, 31))
    assert prev == (date(2026, 2, 1), date(2026, 2, 28))
    assert not partial


def test_partial_month_compares_equal_length_window():
    cur, prev, partial = comparison_periods(date(2026, 3, 12))
    assert partial
    assert cur == (date(2026, 3, 1), date(2026, 3, 12))
    assert prev == (date(2026, 2, 1), date(2026, 2, 12))
    # 31st of a month vs a 30-day previous month is clipped to the month end.
    _, prev, _ = comparison_periods(date(2026, 5, 30))
    assert prev == (date(2026, 4, 1), date(2026, 4, 30))


def test_zero_previous_spending_shows_no_percentage(small_conn):
    comp = compare_periods(small_conn)           # March 1-5 vs February 1-5 (no spending)
    assert comp.is_partial and comp.previous_paise == 0
    assert comp.change_pct is None
    insight = describe_change(comp)
    assert "Spending began this period" == insight.title
    assert "%" not in insight.text


def test_increase_explains_top_driver():
    rows = [("2026-01-05", "ZOMATO", "500", None), ("2026-01-06", "UBER INDIA", "300", None),
            ("2026-02-05", "ZOMATO", "1500", None), ("2026-02-06", "UBER INDIA", "350", None)]
    conn = conn_from_csv(rows_to_csv(rows), period=("2026-01-01", "2026-02-28"))
    comp = compare_periods(conn)
    assert (comp.previous_paise, comp.current_paise) == (800_00, 1850_00)
    assert comp.change_pct == 131.2
    text = describe_change(comp).text
    assert "increased by 131.2%" in text
    assert "Food & Dining contributed the largest share" in text


def test_no_comparison_without_previous_period():
    conn = conn_from_csv(rows_to_csv([("2026-01-05", "ZOMATO", "500", None)]),
                         period=("2026-01-01", "2026-01-31"))
    assert compare_periods(conn) is None


def test_insights_are_consistent_with_sql_metrics(demo_conn):
    items = {i.key: i for i in insights.build_insights(demo_conn)}
    comp = compare_periods(demo_conn)
    monthly = analytics.monthly_summary(demo_conn).set_index("month_start")
    # The comparison uses the same Expenditure definition as the monthly summary.
    assert comp.current_paise == monthly.loc["2026-09-01", "expenditure_paise"]
    assert comp.previous_paise == monthly.loc["2026-08-01", "expenditure_paise"]
    assert comp.change_pct == monthly.loc["2026-09-01", "mom_change_pct"]
    assert "largest_category" in items and "Rent & Housing" in items["largest_category"].text


def test_filters_respected_in_insights(demo_conn):
    items = insights.build_insights(demo_conn, Filters(categories=("Food & Dining",)))
    largest = next(i for i in items if i.key == "largest_category")
    assert "Food & Dining" in largest.text


def test_empty_database_has_no_insights(empty_conn):
    assert insights.build_insights(empty_conn) == []
    assert compare_periods(empty_conn) is None


def test_insights_carry_structured_fields_that_reproduce_them(demo_conn):
    items = {i.key: i for i in insights.build_insights(demo_conn)}
    largest = items["largest_category"]
    assert largest.subject == "Rent & Housing" and largest.value_paise == 10_800_000
    # Following the link gives exactly the amount the insight states.
    link = largest.link
    f = Filters(categories=tuple(link["categories"]), transaction_types=tuple(link["types"]))
    assert analytics.totals(demo_conn, f)["expenditure_paise"] == largest.value_paise
    change = items["overall_change"]
    assert change.value_pct == -60.8 and "September 2026" in change.period
    assert items["top_merchant"].subject == "House Rent"
