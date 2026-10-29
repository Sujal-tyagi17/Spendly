"""Executive KPIs, change explanations, the monthly report, demo reset and API hardening.

Fixture expectations are worked out by hand in the comments; the report is checked
against the dashboard API for the same month and filters.
"""

import io
from datetime import date

import pdfplumber
import pytest
from fastapi.testclient import TestClient

from api import main
from api.state import ConnectionManager, PreviewStore
from src import analytics, budgets, config, database, insights, kpis, report
from src.analytics import Filters
from src.money import format_inr
from tests.test_advanced_analytics import make_conn

# Jan and Feb complete (statement Jan 1 – Feb 28), Mar partial (statement Mar 1 – Mar 10).
#   Jan: Zomato 300, Zomato 500, Amazon 1000            = 1,800 over 3 payments
#   Feb: Zomato 400, Amazon 2000, Amazon 1000, Uber 200 = 3,600 over 4 payments
#   Mar: Zomato 700                                     =   700 (1–10 Mar)
ROWS = [
    ("2026-01-03", "UPI/DR/1/ZOMATO/YESB", "300.00", None),
    ("2026-01-10", "UPI/DR/2/ZOMATO/YESB", "500.00", None),
    ("2026-01-20", "POS/XXXX1111/AMZN MKTPLACE", "1000.00", None),
    ("2026-01-25", "NEFT/CR/6/ACME/SALARY JAN", None, "30000.00"),
    ("2026-02-03", "UPI/DR/3/ZOMATO/YESB", "400.00", None),
    ("2026-02-08", "POS/XXXX1111/AMZN MKTPLACE", "2000.00", None),
    ("2026-02-15", "POS/XXXX1111/AMZN MKTPLACE", "1000.00", None),
    ("2026-02-20", "UPI/DR/4/UBER INDIA/YESB", "200.00", None),
    ("2026-02-21", "IMPS/DR/4/SELF TRANSFER TO OWN A/C", "5000.00", None),
    ("2026-03-02", "UPI/DR/7/ZOMATO/YESB", "700.00", None),
]


@pytest.fixture
def conn():
    return make_conn(ROWS, [("2026-01-01", "2026-02-28"), ("2026-03-01", "2026-03-10")])


# ------------------------------------------------------------------- KPIs

def test_average_monthly_expenditure_uses_complete_months_only(conn):
    s = kpis.executive_summary(conn)
    assert s["expenditure_paise"] == 610000                       # 1,800 + 3,600 + 700
    assert s["average_monthly_expenditure"] == {"value_paise": 270000, "months": 2}   # (1,800 + 3,600) / 2; March partial
    # A filter that cuts January in half leaves only February complete.
    s2 = kpis.executive_summary(conn, Filters(start_date=date(2026, 1, 15)))
    assert s2["average_monthly_expenditure"] == {"value_paise": 360000, "months": 1}


def test_month_over_month_matches_insights(conn):
    f = Filters(end_date=date(2026, 2, 28))
    s = kpis.executive_summary(conn, f)
    comp = insights.compare_periods(conn, f)
    assert s["month_over_month"]["change_pct"] == comp.change_pct == 100.0   # 1,800 → 3,600
    partial = kpis.executive_summary(conn)["month_over_month"]
    assert partial["is_partial"] is True and partial["previous_label"].startswith("Feb 1–10")


def test_no_previous_month_and_empty_data():
    assert kpis.executive_summary(database.connect(":memory:"))["month_over_month"] is None
    s = kpis.executive_summary(database.connect(":memory:"))
    assert s["expenditure_paise"] == 0 and s["average_monthly_expenditure"]["value_paise"] is None
    assert s["budget"] is None


def test_budget_utilisation_overall_and_category_fallback(conn):
    f = Filters(end_date=date(2026, 2, 28))
    budgets.create_budget(conn, "2026-02", "Shopping", "4000")
    b = kpis.executive_summary(conn, f)["budget"]
    assert b["basis"] == "sum of category budgets" and b["utilisation_pct"] == 90.0   # 3,600 / 4,000
    budgets.create_budget(conn, "2026-02", None, "3000")
    b = kpis.executive_summary(conn, f)["budget"]
    assert b["basis"] == "overall budget" and b["utilisation_pct"] == 120.0 and b["status"] == "over"


# ------------------------------------------------------------ explanations

def test_explain_change_decomposition(conn):
    st = kpis.explain_change(conn, Filters(end_date=date(2026, 2, 28)))
    f = st["facts"]
    assert (f["payments_previous"], f["payments_current"]) == (3, 4)
    assert (f["avg_previous_paise"], f["avg_current_paise"]) == (60000, 90000)      # 1,800/3 and 3,600/4
    assert f["count_effect_paise"] == 60000                    # (4 − 3) × ₹600
    assert f["size_effect_paise"] == 120000                    # 4 × (₹900 − ₹600)
    assert f["count_effect_paise"] + f["size_effect_paise"] == f["change_paise"] == 180000
    cats = next(p for p in st["points"] if p["key"] == "categories")["items"]
    assert cats[0] == {"name": "Shopping", "change_paise": 200000, "share_of_change_pct": 111.1}
    assert "not proven causes" in st["caveats"][-1]
    text = " ".join(p["text"] for p in st["points"]).lower()
    assert "because" not in text and "caused" not in text


def test_explain_change_partial_and_missing(conn):
    st = kpis.explain_change(conn)
    assert any("incomplete" in c for c in st["caveats"])        # March 1–10 vs Feb 1–10
    single = make_conn(ROWS[:3], [("2026-01-01", "2026-01-31")])
    assert kpis.explain_change(single)["available"] is False


def test_explain_change_previous_zero():
    c = make_conn([("2026-02-05", "UPI/DR/1/ZOMATO/YESB", "100.00", None)], [("2026-01-01", "2026-02-28")])
    st = kpis.explain_change(c)
    assert st["available"] is True and st["points"] == []
    assert any("no spending" in x for x in st["caveats"])


# ------------------------------------------------------------------ report

def test_report_collects_existing_metrics(conn):
    data = report.build_monthly_report(conn, "2026-02")
    f = Filters(start_date=date(2026, 2, 1), end_date=date(2026, 2, 28))
    t = analytics.totals(conn, f)
    assert data["kpis"]["expenditure_paise"] == t["expenditure_paise"] == 360000
    assert data["kpis"]["income_paise"] == 0
    assert [c["category"] for c in data["categories"]] == list(analytics.category_spending(conn, f)["category"])
    assert data["coverage"]["is_full"] is True and data["is_demo"] is False
    assert [r["month_start"][:7] for r in data["trend"]] == ["2026-01", "2026-02"]


def test_report_empty_and_partial_months(conn):
    empty = report.build_monthly_report(conn, "2026-06")
    assert empty["kpis"]["expenditure_paise"] == 0 and "No imported statement" in empty["limitations"][0]
    partial = report.build_monthly_report(conn, "2026-03")
    assert partial["limitations"][0].startswith("Partial month")
    for d in (empty, partial):
        pdf = report.render_pdf(d)
        assert pdf.startswith(b"%PDF")


def _pdf_text(pdf: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        return "\n".join(page.extract_text() or "" for page in doc.pages)


# ----------------------------------------------------------------------- API

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


@pytest.mark.parametrize("query", ["", "&categories=Groceries&categories=Food%20%26%20Dining"])
def test_report_matches_dashboard_for_same_month_and_filters(client, query):
    overview = client.get(f"/api/overview?start=2026-09-01&end=2026-09-30{query}", headers=DEMO).json()
    data = client.get(f"/api/report/monthly?month=2026-09{query}", headers=DEMO).json()
    ex, rk = overview["executive"], data["kpis"]
    for key in ("expenditure_paise", "income_paise", "net_cash_flow_paise", "refunds_paise", "transaction_count"):
        assert rk[key] == ex[key] == overview["totals"][key]
    assert rk["month_over_month"] == ex["month_over_month"]
    assert rk["budget"] == ex["budget"]
    assert [(c["category"], c["expenditure_paise"]) for c in data["categories"]] == \
           [(c["category"], c["expenditure_paise"]) for c in overview["categories"]]
    assert [m["merchant"] for m in data["top_merchants"]] == [m["merchant"] for m in overview["top_merchants"]]
    assert data["story"]["facts"] == overview["story"]["facts"]

    pdf = client.get(f"/api/report/monthly.pdf?month=2026-09{query}", headers=DEMO)
    assert pdf.headers["content-type"] == "application/pdf"
    assert 'filename="spendly-report-2026-09-demo.pdf"' in pdf.headers["content-disposition"]
    text = _pdf_text(pdf.content)
    assert format_inr(ex["expenditure_paise"]) in text and format_inr(ex["income_paise"]) in text
    assert "SYNTHETIC DEMO DATA" in text and "September 2026" in text


def test_user_report_is_not_labelled_demo(client):
    data = client.get("/api/report/monthly?month=2026-09", headers=USER).json()
    assert data["is_demo"] is False and data["kpis"]["expenditure_paise"] == 0
    text = _pdf_text(client.get("/api/report/monthly.pdf?month=2026-09", headers=USER).content)
    assert "SYNTHETIC" not in text and "No imported statement" in text
    assert client.get("/api/report/monthly?month=2026-13", headers=USER).status_code == 400
    assert client.get("/api/report/monthly?month=" + "9" * 40, headers=USER).status_code == 422


def test_demo_reset_restores_known_state(client):
    before = client.get("/api/overview", headers=DEMO).json()["totals"]
    txn = client.get("/api/transactions?page_size=1", headers=DEMO).json()["rows"][0]
    client.patch(f"/api/transactions/{txn['id']}", json={"category": "Travel"}, headers=DEMO)
    client.delete(f"/api/transactions/{txn['id']}", headers=DEMO)
    client.post("/api/recurring/decision", json={"merchant": "Netflix", "decision": "rejected"}, headers=DEMO)
    assert client.get("/api/overview", headers=DEMO).json()["totals"] != before
    client.post("/api/demo/reset", headers=DEMO)
    after = client.get("/api/overview", headers=DEMO).json()["totals"]
    assert after == before
    assert client.post("/api/demo/reset", headers=USER).status_code == 409   # can't "reset" personal data


def test_delete_all_clears_every_user_table_and_keeps_demo(client, tmp_path):
    from src.sample_pdfs import bank_statement_pdf
    rows, bal = [], 10_000_00
    for i in range(4):
        bal -= 100_00
        rows.append({"date": date(2026, 7, 1 + i), "description": f"UPI/DR/4123{i}/ZOMATO/YESB", "debit": 100_00,
                     "credit": None, "balance": bal})
    tok = client.post("/api/import/preview", headers=USER,
                      files={"file": ("s.pdf", bank_statement_pdf(rows), "application/pdf")}).json()["token"]
    client.post(f"/api/import/{tok}/commit", json={}, headers=USER)
    client.post("/api/budgets", json={"month": "2026-07", "category": None, "amount": "500"}, headers=USER)
    assert client.request("DELETE", "/api/data", json={"confirm": "yes"}, headers=USER).status_code == 400
    assert client.request("DELETE", "/api/data", json={"confirm": "DELETE"}, headers=DEMO).status_code == 409
    assert client.request("DELETE", "/api/data", json={"confirm": "DELETE"}, headers=USER).json() == {"ok": True}
    with main.connections.connection("user", None) as conn:
        for table in ("transactions", "statements", "import_issues", "budgets", "manual_corrections",
                      "anomaly_reviews", "recurring_decisions"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
    assert client.get("/api/meta", headers=DEMO).json()["counts"]["transactions"] == 284


def test_security_headers_and_validation(client):
    r = client.get("/api/overview", headers=DEMO)
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert client.get("/api/overview?start=2026-09-30&end=2026-09-01", headers=DEMO).status_code == 400
    assert client.get("/api/transactions?merchants=" + "x" * 200, headers=DEMO).status_code == 400
    assert client.get("/api/overview", headers={"X-Spendly-Mode": "admin"}).status_code == 400
    bad = client.get("/api/transactions?statuses=everything", headers=DEMO)
    assert bad.status_code == 400 and "Traceback" not in bad.text


def test_public_mode_cannot_touch_another_sessions_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "connections", ConnectionManager(public=True))
    with TestClient(main.app) as c:
        a = {**DEMO, "X-Spendly-Session": c.post("/api/session").json()["session"]}
        b = {**DEMO, "X-Spendly-Session": c.post("/api/session").json()["session"]}
        txn = c.get("/api/transactions?page_size=1", headers=a).json()["rows"][0]
        # B uses A's transaction id: it only ever reaches B's own private database.
        c.delete(f"/api/transactions/{txn['id']}", headers=b)
        assert c.get("/api/meta", headers=a).json()["counts"]["transactions"] == 284
        assert c.get("/api/meta", headers=b).json()["counts"]["transactions"] == 283
        assert c.get("/api/meta", headers={**DEMO, "X-Spendly-Session": "../../etc"}).status_code == 401
    main.connections.close_all()


def test_api_docs_hidden_on_public_deployments(monkeypatch):
    import importlib
    monkeypatch.setenv("SPENDLY_PUBLIC_DEPLOYMENT", "true")
    monkeypatch.delenv("SPENDLY_API_DOCS", raising=False)
    import api.main as m
    reloaded = importlib.reload(m)
    try:
        with TestClient(reloaded.app) as c:
            assert c.get("/api/docs").status_code == 404
    finally:
        monkeypatch.setenv("SPENDLY_PUBLIC_DEPLOYMENT", "false")
        importlib.reload(m)
