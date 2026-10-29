"""Budget planner tests. Expected values are worked out by hand from the fixture below,
never produced by the SQL under test.

January 2026 fixture (one statement covering 1–31 Jan), rupees:
  03 Zomato       300   Food & Dining
  05 Amazon      1000   Shopping
  08 Amazon refund 400 cr  (Refunds — NOT netted against Shopping)
  09 BigBasket    800   Groceries
  10 Uber         200   Transport
  expenditure = 2,300   refunds = 400   net = 1,900
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import pytest
from fastapi.testclient import TestClient

from api import main
from api.state import ConnectionManager, PreviewStore
from src import analytics, budgets, config, database
from src.analytics import Filters
from tests.test_advanced_analytics import make_conn

ROWS = [
    ("2026-01-03", "UPI/DR/1/ZOMATO/YESB", "300.00", None),
    ("2026-01-05", "POS/XXXX1111/AMZN MKTPLACE", "1000.00", None),
    ("2026-01-08", "UPI/CR/5/AMAZON REFUND/UTIB", None, "400.00"),
    ("2026-01-09", "UPI/DR/9/BIGBASKET/YESB", "800.00", None),
    ("2026-01-10", "UPI/DR/9/UBER INDIA/YESB", "200.00", None),
]
JAN = "2026-01"


@pytest.fixture
def conn():
    return make_conn(ROWS, [("2026-01-01", "2026-01-31")])


@pytest.fixture
def budgeted(conn):
    budgets.create_budget(conn, JAN, "Shopping", "1000")       # equal to actual
    budgets.create_budget(conn, JAN, "Food & Dining", "200")   # 300 spent → over by 100
    budgets.create_budget(conn, JAN, "Groceries", "1000")      # 800 spent → 80% → near
    budgets.create_budget(conn, JAN, "Transport", "0")         # zero budget, 200 spent
    budgets.create_budget(conn, JAN, "Entertainment", "500")   # nothing spent
    budgets.create_budget(conn, JAN, None, "3000")             # overall
    return conn


def _row(report, category):
    return next(r for r in report["rows"] if r["category"] == category)


# --------------------------------------------------------------- validation

@pytest.mark.parametrize("text,expected", [("2026-09", "2026-09-01"), ("2026-09-01", "2026-09-01"),
                                           (" 2026-12 ", "2026-12-01")])
def test_normalize_month(text, expected):
    assert budgets.normalize_month(text) == expected


@pytest.mark.parametrize("bad", ["", "2026-13", "2026-00", "1999-05", "Sept 2026", "2026-09-15", None])
def test_invalid_months_rejected(bad):
    with pytest.raises(budgets.BudgetError):
        budgets.normalize_month(bad)


@pytest.mark.parametrize("bad", ["-100", "(100)", "abc", "", None, True, "1,00,00,00,000"])
def test_invalid_amounts_rejected(conn, bad):
    with pytest.raises(budgets.BudgetError):
        budgets.create_budget(conn, JAN, "Shopping", bad)
    assert budgets.list_budgets(conn, JAN) == []


def test_amount_stored_as_integer_paise(conn):
    bid = budgets.create_budget(conn, JAN, "Shopping", "₹1,234.50")
    assert budgets.get_budget(conn, bid)["amount_paise"] == 123450
    bid2 = budgets.create_budget(conn, JAN, "Groceries", 99.99)
    assert budgets.get_budget(conn, bid2)["amount_paise"] == 9999


@pytest.mark.parametrize("category", ["Income", "Transfers", "Refunds", "Made Up"])
def test_non_spending_categories_rejected(conn, category):
    with pytest.raises(budgets.BudgetError):
        budgets.create_budget(conn, JAN, category, "100")


def test_duplicates_rejected_per_category_and_month(conn):
    budgets.create_budget(conn, JAN, "Shopping", "100")
    with pytest.raises(budgets.DuplicateBudgetError):
        budgets.create_budget(conn, JAN, "Shopping", "200")
    budgets.create_budget(conn, "2026-02", "Shopping", "200")  # other month is fine
    budgets.create_budget(conn, JAN, None, "1000")
    with pytest.raises(budgets.DuplicateBudgetError):  # NULL category is unique too
        budgets.create_budget(conn, JAN, None, "2000")


def test_database_constraints_back_up_validation(conn):
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO budgets (month, category, amount_paise, created_at, updated_at) "
                     "VALUES ('2026-01-01', 'Shopping', -5, 'x', 'x')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO budgets (month, category, amount_paise, created_at, updated_at) "
                     "VALUES ('2026-01-15', 'Shopping', 5, 'x', 'x')")


# ----------------------------------------------------------- create / edit

def test_edit_and_delete(conn):
    bid = budgets.create_budget(conn, JAN, "Shopping", "100")
    budgets.update_budget(conn, bid, "250.75")
    assert budgets.get_budget(conn, bid)["amount_paise"] == 25075
    with pytest.raises(budgets.BudgetError):
        budgets.update_budget(conn, bid, "-1")
    assert budgets.get_budget(conn, bid)["amount_paise"] == 25075  # unchanged after a bad edit
    budgets.delete_budget(conn, bid)
    assert budgets.get_budget(conn, bid) is None
    with pytest.raises(budgets.BudgetError):
        budgets.delete_budget(conn, bid)


def test_budgets_persist_across_connections(tmp_path):
    path = tmp_path / "s.db"
    c1 = database.connect(path)
    bid = budgets.create_budget(c1, JAN, "Shopping", "500")
    c1.close()
    c2 = database.connect(path)
    assert budgets.get_budget(c2, bid)["amount_paise"] == 50000
    budgets.delete_budget(c2, bid)
    c2.close()
    assert budgets.list_budgets(database.connect(path), JAN) == []


def test_copy_from_previous_month(budgeted):
    budgets.create_budget(budgeted, "2026-02", "Shopping", "9999")
    result = budgets.copy_budgets(budgeted, JAN, "2026-02")
    assert result == {"created": 5, "updated": 0, "skipped": 1, "source_count": 6}
    feb = {b["category"]: b["amount_paise"] for b in budgets.list_budgets(budgeted, "2026-02")}
    assert feb["Shopping"] == 999900  # kept, not overwritten
    assert feb[None] == 300000 and feb["Food & Dining"] == 20000
    result = budgets.copy_budgets(budgeted, JAN, "2026-02", overwrite=True)
    assert result["updated"] == 6 and result["created"] == 0
    assert {b["category"]: b["amount_paise"] for b in budgets.list_budgets(budgeted, "2026-02")}["Shopping"] == 100000
    with pytest.raises(budgets.BudgetError):
        budgets.copy_budgets(budgeted, JAN, JAN)


# ---------------------------------------------------------------- metrics

def test_spending_equal_to_budget_is_at_limit(budgeted):
    r = _row(budgets.month_report(budgeted, JAN), "Shopping")
    assert (r["budget_paise"], r["actual_paise"]) == (100000, 100000)
    assert r["remaining_paise"] == 0 and r["variance_paise"] == 0
    assert r["utilisation_pct"] == 100.0 and r["status"] == "at_limit"


def test_spending_above_budget(budgeted):
    r = _row(budgets.month_report(budgeted, JAN), "Food & Dining")
    assert r["actual_paise"] == 30000 and r["variance_paise"] == 10000 and r["remaining_paise"] == -10000
    assert r["utilisation_pct"] == 150.0 and r["variance_pct"] == 50.0 and r["status"] == "over"


def test_near_threshold(budgeted):
    r = _row(budgets.month_report(budgeted, JAN), "Groceries")
    assert r["utilisation_pct"] == 80.0 and r["status"] == "near"


def test_zero_budget_does_not_divide(budgeted):
    r = _row(budgets.month_report(budgeted, JAN), "Transport")
    assert r["budget_paise"] == 0 and r["actual_paise"] == 20000
    assert r["utilisation_pct"] is None and r["variance_pct"] is None
    assert r["variance_paise"] == 20000 and r["status"] == "over"
    assert budgets.status_for(0, 0, True) == "within"


def test_budgeted_category_with_no_spending(budgeted):
    r = _row(budgets.month_report(budgeted, JAN), "Entertainment")
    assert r["actual_paise"] == 0 and r["transaction_count"] == 0
    assert r["remaining_paise"] == 50000 and r["utilisation_pct"] == 0.0 and r["status"] == "within"


def test_unbudgeted_spending_listed(conn):
    budgets.create_budget(conn, JAN, "Shopping", "5000")
    report = budgets.month_report(conn, JAN)
    unbudgeted = {r["category"]: r for r in report["rows"] if r["budget_paise"] is None}
    assert set(unbudgeted) == {"Food & Dining", "Groceries", "Transport"}
    assert all(r["status"] == "no_budget" and r["remaining_paise"] is None for r in unbudgeted.values())
    assert report["overall"]["unbudgeted_paise"] == 30000 + 80000 + 20000


def test_refunds_are_not_netted_against_categories(budgeted):
    report = budgets.month_report(budgeted, JAN)
    assert _row(report, "Shopping")["actual_paise"] == 100000  # the 400 refund does not reduce it
    assert all(r["category"] != "Refunds" for r in report["rows"])
    o = report["overall"]
    assert o["expenditure_paise"] == 230000 and o["refunds_paise"] == 40000 and o["net_expenditure_paise"] == 190000
    assert o["remaining_paise"] == 70000 and o["utilisation_pct"] == 76.7
    assert o["status"] == "within" and o["category_budgets_paise"] == 100000 + 20000 + 100000 + 0 + 50000


def test_transfers_and_income_never_count(conn):
    rows = ROWS + [("2026-01-15", "IMPS/DR/4/SELF TRANSFER TO OWN A/C", "5000.00", None),
                   ("2026-01-20", "NEFT/CR/6/ACME/SALARY JAN", None, "30000.00"),
                   ("2026-01-21", "BILLDESK/CREDIT CARD PAYMENT", "3000.00", None)]
    c = make_conn(rows, [("2026-01-01", "2026-01-31")])
    assert budgets.month_report(c, JAN)["overall"]["expenditure_paise"] == 230000


def test_missing_month_is_no_data_not_zero(budgeted):
    budgets.copy_budgets(budgeted, JAN, "2026-02")
    report = budgets.month_report(budgeted, "2026-02")
    assert report["coverage"]["is_covered"] is False
    assert all(r["status"] == "no_data" for r in report["rows"])
    assert report["overall"]["status"] == "no_data"
    assert budgets.insights(budgeted, "2026-02", report)[0]["key"] == "no_data"


def test_empty_database(tmp_path):
    c = database.connect(":memory:")
    report = budgets.month_report(c, JAN)
    assert report["rows"] == [] and report["overall"]["expenditure_paise"] == 0
    assert report["overall"]["status"] == "no_data"
    assert budgets.history(c, JAN) == []


def test_sql_matches_category_spending(budgeted):
    """Budget actuals must equal the existing analytics for the same month."""
    report = budgets.month_report(budgeted, JAN)
    f = Filters(start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
    cats = analytics.category_spending(budgeted, f).set_index("category")["expenditure_paise"].to_dict()
    assert {r["category"]: r["actual_paise"] for r in report["rows"] if r["actual_paise"]} == cats
    assert report["overall"]["expenditure_paise"] == analytics.totals(budgeted, f)["expenditure_paise"]


def test_demo_dataset_matches_analytics(demo_conn):
    for month in ("2026-07", "2026-08", "2026-09"):
        start, end = budgets.month_bounds(month)
        f = Filters(start_date=start, end_date=end)
        report = budgets.month_report(demo_conn, month)
        cats = analytics.category_spending(demo_conn, f).set_index("category")["expenditure_paise"].to_dict()
        assert {r["category"]: r["actual_paise"] for r in report["rows"] if r["actual_paise"]} == cats
        for r in report["rows"]:
            if r["budget_paise"]:
                assert r["remaining_paise"] == r["budget_paise"] - r["actual_paise"]
                exact = Decimal(100 * r["actual_paise"]) / Decimal(r["budget_paise"])
                assert r["utilisation_pct"] == float(exact.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def test_demo_budgets_seeded(demo_conn):
    sep = budgets.month_report(demo_conn, "2026-09")
    assert _row(sep, "Groceries")["status"] == "over"
    assert _row(sep, "Rent & Housing")["status"] == "at_limit"
    assert budgets.list_budgets(demo_conn, "2026-06") == []


# ------------------------------------------------------------------- pace

def test_pace_estimate_for_partial_month():
    c = make_conn(ROWS, [("2026-01-01", "2026-01-10")])
    budgets.create_budget(c, JAN, None, "3000")
    report = budgets.month_report(c, JAN)
    assert report["coverage"]["is_full"] is False and report["coverage"]["days_covered"] == 10
    pace = report["overall"]["pace"]
    assert pace["is_estimate"] is True
    assert pace["projected_paise"] == round(230000 * 31 / 10)
    assert pace["expected_to_date_paise"] == round(300000 * 10 / 31)
    assert pace["pace"] == "faster" and pace["days_remaining"] == 21
    keys = {i["key"]: i for i in budgets.insights(c, JAN, report)}
    assert keys["pace"]["kind"] == "estimate"
    assert all(i["kind"] == "observed" for k, i in keys.items() if k != "pace")


def test_no_pace_with_too_few_days_or_full_month(budgeted):
    c = make_conn(ROWS, [("2026-01-01", "2026-01-05")])
    budgets.create_budget(c, JAN, None, "3000")
    assert budgets.month_report(c, JAN)["overall"]["pace"] is None  # 5 < pace_min_days
    assert budgets.month_report(budgeted, JAN)["overall"]["pace"] is None  # complete month: no projection


def test_no_pace_when_data_starts_mid_month():
    c = make_conn([r for r in ROWS if r[0] >= "2026-01-05"], [("2026-01-05", "2026-01-31")])
    budgets.create_budget(c, JAN, None, "3000")
    assert budgets.month_report(c, JAN)["overall"]["pace"] is None


# --------------------------------------------------------------- insights

def test_insights_are_observations(budgeted):
    found = {i["key"]: i for i in budgets.insights(budgeted, JAN)}
    assert {"overall", "over", "largest_overspend", "near"} <= set(found)
    # Ranked by rupees over budget: Transport (₹200 over a ₹0 budget) beats Food (₹100 over).
    assert found["largest_overspend"]["text"] == "Transport: ₹200 spent vs ₹0 budgeted (₹200 over)."
    assert "Transport, Food & Dining" in found["over"]["text"]
    for i in found.values():
        assert i["kind"] == "observed"
        lowered = i["text"].lower()
        assert not any(word in lowered for word in ("unhealthy", "bad", "should", "irresponsible"))


def test_threshold_is_configurable(budgeted, monkeypatch):
    monkeypatch.setattr(config, "BUDGET", config.BudgetSettings(near_threshold_pct=90))
    assert _row(budgets.month_report(budgeted, JAN), "Groceries")["status"] == "within"


def test_repeated_overspending_and_utilisation_change():
    rows = [("2026-01-05", "UPI/DR/1/ZOMATO/YESB", "300.00", None),
            ("2026-02-05", "UPI/DR/2/ZOMATO/YESB", "500.00", None),
            ("2026-03-05", "UPI/DR/3/ZOMATO/YESB", "100.00", None)]
    c = make_conn(rows, [("2026-01-01", "2026-03-31")])
    for m in ("2026-01", "2026-02", "2026-03"):
        budgets.create_budget(c, m, "Food & Dining", "200")
    found = {i["key"]: i for i in budgets.insights(c, "2026-03")}
    assert "Food & Dining" in found["repeated"]["text"]  # over in Jan and Feb
    # Mar 50% vs Feb 250% → 200 points less
    assert "200 percentage points less" in found["utilisation_change"]["text"]


# -------------------------------------------------------------------- API

DEMO = {"X-Spendly-Mode": "demo"}
USER = {"X-Spendly-Mode": "user"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "connections", ConnectionManager(public=False))
    monkeypatch.setattr(main, "previews", PreviewStore())
    with TestClient(main.app) as c:
        yield c
    main.connections.close_all()


def test_api_crud_and_errors(client):
    r = client.post("/api/budgets", json={"month": "2026-09", "category": "Shopping", "amount": "100"}, headers=USER)
    assert r.status_code == 201
    bid = r.json()["id"]
    assert client.post("/api/budgets", json={"month": "2026-09", "category": "Shopping", "amount": "5"},
                       headers=USER).status_code == 409
    assert client.post("/api/budgets", json={"month": "2026-09", "category": "Shopping", "amount": "-5"},
                       headers=USER).status_code == 400
    assert client.post("/api/budgets", json={"month": "nope-123", "amount": "5"}, headers=USER).status_code == 400
    assert client.patch(f"/api/budgets/{bid}", json={"amount": "250"}, headers=USER).json()["amount_paise"] == 25000
    assert client.patch("/api/budgets/99999", json={"amount": "1"}, headers=USER).status_code == 404
    assert client.delete(f"/api/budgets/{bid}", headers=USER).json() == {"ok": True}
    assert client.delete(f"/api/budgets/{bid}", headers=USER).status_code == 404


def test_api_report_matches_module(client):
    j = client.get("/api/budgets?month=2026-09", headers=DEMO).json()
    with main.connections.connection("demo", None) as conn:
        expected = budgets.month_report(conn, "2026-09")
    assert j["overall"]["expenditure_paise"] == expected["overall"]["expenditure_paise"]
    assert [(r["category"], r["actual_paise"], r["budget_paise"]) for r in j["rows"]] == \
           [(r["category"], r["actual_paise"], r["budget_paise"]) for r in expected["rows"]]
    assert j["insights"] and j["history"] and "Income" not in j["categories"]
    d = client.get("/api/budgets/drivers?month=2026-09&category=Groceries", headers=DEMO).json()
    assert sum(m["expenditure_paise"] for m in d["merchants"]) == _row(expected, "Groceries")["actual_paise"]
    assert client.get("/api/budgets/drivers?category=Income", headers=DEMO).status_code == 400
    months = client.get("/api/budgets/months", headers=DEMO).json()
    assert months["default"] == "2026-09" and months["months"][0]["has_budgets"] is True


def test_api_demo_and_user_isolated(client):
    assert client.get("/api/budgets?month=2026-09", headers=USER).json()["overall"]["overall_budget_paise"] is None
    client.post("/api/budgets", json={"month": "2026-09", "category": None, "amount": "1"}, headers=USER)
    assert client.get("/api/budgets?month=2026-09", headers=DEMO).json()["overall"]["overall_budget_paise"] == 5000000
    # Demo reset restores the seeded budgets after demo edits.
    bid = client.get("/api/budgets?month=2026-09", headers=DEMO).json()["overall"]["overall_budget_id"]
    client.delete(f"/api/budgets/{bid}", headers=DEMO)
    client.post("/api/demo/reset", headers=DEMO)
    assert client.get("/api/budgets?month=2026-09", headers=DEMO).json()["overall"]["overall_budget_paise"] == 5000000
    assert client.get("/api/budgets?month=2026-09", headers=USER).json()["overall"]["overall_budget_paise"] == 100


def test_api_public_sessions_isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "connections", ConnectionManager(public=True))
    with TestClient(main.app) as c:
        sa, sb = c.post("/api/session").json()["session"], c.post("/api/session").json()["session"]
        a = {**USER, "X-Spendly-Session": sa}
        b = {**USER, "X-Spendly-Session": sb}
        assert c.get("/api/budgets", headers=USER).status_code == 401  # session required
        c.post("/api/budgets", json={"month": "2026-09", "category": "Shopping", "amount": "100"}, headers=a)
        assert len([r for r in c.get("/api/budgets?month=2026-09", headers=a).json()["rows"] if r["budget_id"]]) == 1
        assert c.get("/api/budgets?month=2026-09", headers=b).json()["rows"] == []
        da = {**DEMO, "X-Spendly-Session": sa}
        db = {**DEMO, "X-Spendly-Session": sb}
        bid = c.get("/api/budgets?month=2026-09", headers=da).json()["overall"]["overall_budget_id"]
        c.patch(f"/api/budgets/{bid}", json={"amount": "1"}, headers=da)
        assert c.get("/api/budgets?month=2026-09", headers=db).json()["overall"]["overall_budget_paise"] == 5000000
    assert not list(tmp_path.glob("*.db"))
    main.connections.close_all()


def test_api_copy(client):
    r = client.post("/api/budgets/copy", json={"from_month": "2026-09", "to_month": "2026-10"}, headers=DEMO)
    assert r.json()["created"] == 9
    assert client.post("/api/budgets/copy", json={"from_month": "2026-09", "to_month": "2026-09"},
                       headers=DEMO).status_code == 400
