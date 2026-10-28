"""Data-quality dimensions, import reports and parser evaluation.

Every expected number is counted by hand from the fixture rows written out in
each test, never taken from the code under test.
"""

import json
import sqlite3
from datetime import date

import pytest
from fastapi.testclient import TestClient

from api import main
from api.state import ConnectionManager, PreviewStore
from src import analytics, config, database, parser_eval, pipeline, quality
from src.analytics import Filters
from src.sample_pdfs import bank_statement_pdf, phonepe_statement_pdf
from src.transaction_normalizer import RawRow

HEADER = "date,description,debit,credit,balance\n"


def preview_csv(body: str, conn=None):
    return pipeline.prepare_csv_rows_import(HEADER + body, display_name="t", conn=conn)


def raw(date_text, desc, debit=None, credit=None, balance=None, n=1):
    return RawRow(date_text=date_text, description=desc, debit_text=debit, credit_text=credit,
                  balance_text=balance, row_number=n)


def preview_raw(rows, formats=("%d/%m/%Y", "%m/%d/%Y"), conn=None):
    return pipeline._process(rows, None, display_name="t", file_hash="h", date_formats=formats, conn=conn,
                             parser_name="test", parser_label="test", period=(None, None), extra_warnings=[])


def commit(body: str, conn=None):
    conn = conn or database.connect(":memory:")
    pipeline.commit_import(conn, preview_csv(body, conn))
    return conn


def dim(card, key):
    return next(d for d in card["dimensions"] if d["key"] == key)


# ------------------------------------------------------------ missing fields

def test_missing_fields_and_completeness():
    body = ("2026-01-01,UPI/DR/1/ZOMATO/YESB,100.00,,\n"
            ",UPI/DR/2/ZOMATO/YESB,100.00,,\n"          # missing date
            "2026-01-03,UPI/DR/3/ZOMATO/YESB,,,\n"      # missing amount
            "2026-01-04,,100.00,,\n"                    # missing description
            "2026-01-05,UPI/DR/5/UBER INDIA/YESB,200.00,,\n")
    r = quality.import_report(preview_csv(body))
    assert (r["rows_extracted"], r["rows_rejected"], r["rows_accepted"]) == (5, 3, 2)
    assert r["rejected_by_reason"]["missing_date"] == 1
    assert r["rejected_by_reason"]["missing_amount"] == 1
    assert r["rejected_by_reason"]["missing_description"] == 1
    assert r["rows_complete"] == 2
    assert r["dimensions"]["completeness_pct"] == 40.0       # 2 / 5
    assert r["dimensions"]["validity_pct"] == 100.0          # 2 accepted / 2 complete


def test_row_missing_two_fields_is_counted_once():
    r = quality.import_report(preview_csv(",,100.00,,\n2026-01-02,UPI/DR/1/ZOMATO/YESB,50.00,,\n"))
    assert r["rows_rejected"] == 1
    assert sum(r["rejected_by_reason"].values()) == 1           # primary reason only
    assert r["field_issues"]["missing_date"] == 1 and r["field_issues"]["missing_description"] == 1


def test_zero_amount_is_not_missing():
    r = quality.import_report(preview_csv("2026-01-01,UPI/DR/1/ZOMATO/YESB,0.00,,\n2026-01-02,UPI/DR/2/ZOMATO/YESB,,,\n"))
    assert r["rejected_by_reason"]["zero_amount"] == 1
    assert r["rejected_by_reason"]["missing_amount"] == 1
    # A zero is a present value: that row is complete but invalid.
    assert r["rows_complete"] == 1 and r["dimensions"]["completeness_pct"] == 50.0
    assert r["dimensions"]["validity_pct"] == 0.0


def test_zero_in_unused_column_is_fine():
    p = preview_csv("2026-01-01,UPI/DR/1/ZOMATO/YESB,0.00,250.00,\n")
    assert len(p.rows) == 1 and p.rows[0]["amount_paise"] == 25000 and p.rows[0]["direction"] == "credit"


# ------------------------------------------------------------------- dates

def test_invalid_and_ambiguous_dates():
    p = preview_raw([raw("31/02/2026", "UPI/DR/1/ZOMATO", "100", n=1),     # not a real date in either format
                     raw("04/05/2026", "UPI/DR/2/ZOMATO", "100", n=2),     # 4 May or 5 April
                     raw("25/05/2026", "UPI/DR/3/ZOMATO", "100", n=3)])    # only day-first works
    r = quality.import_report(p)
    assert r["rejected_by_reason"]["invalid_date"] == 1
    assert r["rejected_by_reason"]["ambiguous_date"] == 1
    assert r["rows_accepted"] == 1 and p.rows[0]["transaction_date"] == "2026-05-25"
    codes = {i["code"]: i for i in r["issues"]}
    assert codes["ambiguous_date"]["severity"] == "error"


@pytest.mark.parametrize("text,code", [
    ("Date: missing date", "missing_date"), ("Date: ambiguous date: '04/05/26'", "ambiguous_date"),
    ("Date: unrecognised or out-of-range date: 'x'", "invalid_date"), ("Description: missing", "missing_description"),
    ("Amount: missing", "missing_amount"), ("Amount: zero — no money moved", "zero_amount"),
    ("Amount: both debit and credit are filled", "invalid_amount"), ("Balance: unreadable value", "invalid_balance"),
])
def test_issue_classification(text, code):
    assert quality.classify_issue(text) == code


# -------------------------------------------------------------- duplicates

def test_exact_duplicate_in_file_is_skipped_and_not_a_balance_break():
    body = ("2026-01-01,UPI/DR/1/ZOMATO/YESB,100.00,,900.00\n"
            "2026-01-02,UPI/DR/2/UBER INDIA/YESB,50.00,,850.00\n"
            "2026-01-02,UPI/DR/2/UBER INDIA/YESB,50.00,,850.00\n"   # re-extracted copy
            "2026-01-03,UPI/DR/3/ZOMATO/YESB,25.00,,825.00\n")
    p = preview_csv(body)
    r = quality.import_report(p)
    assert r["exact_duplicates_found"] == 1 and r["exact_duplicates_skipped"] == 1
    assert r["rows_accepted"] == 4 and r["rows_to_import"] == 3
    assert r["dimensions"]["uniqueness_pct"] == 75.0             # 3 / 4
    assert r["balance_check"]["checked_pairs"] == 2 and r["balance_check"]["mismatches"] == 0
    assert p.quality.balance_check.repeated_rows_skipped == 1


def test_possible_duplicate_is_not_a_confirmed_duplicate():
    body = ("2026-01-01,UPI/DR/1/CHAI POINT/YESB,20.00,,\n"
            "2026-01-01,UPI/DR/2/CHAI POINT/YESB,20.00,,\n")
    conn = commit(body)
    card = quality.scorecard(conn)
    assert dim(card, "uniqueness")["value_pct"] == 100.0       # nothing proven to be a copy
    assert "1 possible duplicate" in dim(card, "uniqueness")["note"]
    assert database.count_transactions(conn) == 2              # both kept


def test_buckets_add_up_and_flags_are_not_summed():
    body = ("2026-01-01,UPI/DR/1/ZOMATO/YESB,100.00,,900.00\n"
            "2026-01-01,UPI/DR/1/ZOMATO/YESB,100.00,,900.00\n"
            ",UPI/DR/x/ZOMATO/YESB,1.00,,\n"
            "2026-01-02,UPI/DR/2/MYSTERY SHOP 77/YESB,40.00,,860.00\n")
    r = quality.import_report(preview_csv(body))
    assert r["rows_extracted"] == r["rows_rejected"] + r["rows_accepted"]
    assert r["rows_accepted"] == r["rows_to_import"] + r["exact_duplicates_skipped"]
    assert sum(r["rejected_by_reason"].values()) == r["rows_rejected"]


# ------------------------------------------------------------------ balance

def test_balance_mismatch_is_flagged_on_the_row_and_linkable():
    body = ("2026-01-01,UPI/DR/1/ZOMATO/YESB,100.00,,900.00\n"
            "2026-01-02,UPI/DR/2/UBER INDIA/YESB,50.00,,800.00\n"   # should be 850
            "2026-01-03,UPI/DR/3/ZOMATO/YESB,25.00,,775.00\n")
    conn = commit(body)
    card = quality.scorecard(conn)
    c = dim(card, "consistency")
    assert (c["numerator"], c["denominator"], c["value_pct"]) == (1, 2, 50.0)
    flagged = analytics.transactions(conn, Filters(statuses=("balance_mismatch",)))
    assert list(flagged["amount_paise"]) == [5000]
    assert next(i for i in card["issues"] if i["code"] == "balance_mismatch")["current_count"] == 1


def test_statement_without_running_balance():
    conn = commit("2026-01-01,UPI/DR/1/ZOMATO/YESB,100.00,,\n2026-01-02,UPI/DR/2/ZOMATO/YESB,80.00,,\n")
    card = quality.scorecard(conn)
    c = dim(card, "consistency")
    assert c["denominator"] == 0 and c["value_pct"] is None and "couldn't be measured" in c["note"]
    assert any(i["code"] == "no_balance_column" and i["severity"] == "info" for i in card["issues"])


# ----------------------------------------------------------- reconciliation

def _bank(n=6):
    rows, bal = [], 10_000_00
    for i in range(n):
        credit = i == 2
        amt = 1_500_00 if credit else 100_00 * (i + 1)
        bal += amt if credit else -amt
        rows.append({"date": date(2026, 7, 1 + i), "description": f"UPI/DR/41234{i}/ZOMATO/YESB" if not credit
                     else "UPI/CR/9/AMAZON REFUND/UTIB", "debit": None if credit else amt,
                     "credit": amt if credit else None, "balance": bal})
    return rows


def test_reconciliation_with_printed_balances_and_refund():
    rows = _bank()
    debits = sum(r["debit"] or 0 for r in rows)    # 100+200+400+500+600 = 1,800
    credits = 1_500_00
    closing = 10_000_00 + credits - debits
    p = pipeline.prepare_pdf_import(bank_statement_pdf(rows, opening_balance=10_000_00, closing_balance=closing),
                                    "s.pdf", conn=None)
    rec = quality.import_report(p)["reconciliation"]
    assert rec["opening_paise"] == 10_000_00 and rec["closing_paise"] == 9_700_00
    assert (rec["credits_paise"], rec["debits_paise"]) == (1_500_00, 1_800_00)
    assert rec["difference_paise"] == 0 and rec["reconciled"] is True
    assert any(r["transaction_type"] == "refund" for r in p.rows)


def test_reconciliation_difference_is_reported_as_error():
    rows = _bank()
    pdf = bank_statement_pdf(rows[:-1], opening_balance=10_000_00, closing_balance=rows[-1]["balance"])  # last row missing
    p = pipeline.prepare_pdf_import(pdf, "s.pdf", conn=None)
    r = quality.import_report(p)
    assert r["reconciliation"]["difference_paise"] == 600_00     # the missing ₹600 debit
    item = next(i for i in r["issues"] if i["code"] == "reconciliation_difference")
    assert item["severity"] == "error"
    assert any("closing balance" in w for w in p.warnings)
    conn = database.connect(":memory:")
    pipeline.commit_import(conn, p)
    rc = dim(quality.scorecard(conn), "reconciliation")
    assert (rc["numerator"], rc["denominator"]) == (0, 1)


def test_balances_are_never_inferred():
    p = pipeline.prepare_pdf_import(bank_statement_pdf(_bank()), "s.pdf", conn=None)
    assert p.reconciliation.available is False and p.reconciliation.difference_paise is None


# ---------------------------------------------------------- PDF structures

def test_multipage_wrapped_report():
    rows = []
    bal = 1_00_000_00
    for i in range(110):
        bal -= 100_00
        rows.append({"date": date(2026, 7, 1 + i % 28), "description": f"UPI/DR/5{i:05d}/ZOMATO/YESB",
                     "debit": 100_00, "credit": None, "balance": bal})
    p = pipeline.prepare_pdf_import(bank_statement_pdf(rows, wrap_first_description=True), "s.pdf", conn=None)
    r = quality.import_report(p)
    assert r["rows_extracted"] == 110 and r["rows_rejected"] == 0
    assert r["balance_check"]["checked_pairs"] == 109 and r["balance_check"]["mismatches"] == 0
    assert "MONTHLY PAYMENT" in p.rows[0]["description"]


def test_phonepe_has_no_balance_dimension():
    pp = [{"date": date(2026, 8, 1 + i), "details": "Paid to Zomato", "direction": "debit", "amount": 100_00 + i,
           "txn_id": f"T{i:012d}"} for i in range(5)]
    r = quality.import_report(pipeline.prepare_pdf_import(phonepe_statement_pdf(pp), "p.pdf", conn=None))
    assert r["balance_check"]["available"] is False
    assert r["dimensions"]["balance_consistency_pct"] is None
    assert r["flags"]["rows_without_balance"] == 5


# ------------------------------------------------------------- empty data

def test_empty_statement_has_no_percentages():
    p = preview_csv("")
    r = quality.import_report(p)
    assert r["rows_extracted"] == 0
    assert all(v is None for v in r["dimensions"].values())


def test_empty_database_scorecard():
    card = quality.scorecard(database.connect(":memory:"))
    assert all(d["value_pct"] is None for d in card["dimensions"])
    assert card["trend"] == [] and card["trend_available"] is False


# ------------------------------------------------------------------ scorecard

def test_scorecard_matches_stored_reports_and_trend(tmp_path):
    conn = commit("2026-01-01,UPI/DR/1/ZOMATO/YESB,100.00,,\n,UPI/DR/2/ZOMATO/YESB,5.00,,\n")
    pipeline.commit_import(conn, pipeline.prepare_csv_rows_import(
        HEADER + "2026-02-01,UPI/DR/3/ZOMATO/YESB,100.00,,\n2026-02-02,UPI/DR/4/MYSTERY 42/YESB,9.00,,\n",
        display_name="second", conn=conn))
    card = quality.scorecard(conn)
    comp = dim(card, "completeness")
    assert (comp["numerator"], comp["denominator"], comp["value_pct"]) == (3, 4, 75.0)
    assert card["trend_available"] is True and [t["rows_rejected"] for t in card["trend"]] == [1, 0]
    second = card["statements"][1]["id"]
    one = quality.scorecard(conn, second)
    assert dim(one, "completeness")["value_pct"] == 100.0 and one["scope"]["transactions"] == 2
    cat = dim(one, "categorisation")
    assert (cat["numerator"], cat["denominator"]) == (1, 2)   # "MYSTERY 42" has no rule


def test_no_composite_score():
    card = quality.scorecard(database.connect(":memory:"))
    assert not any(k in card for k in ("score", "overall_score", "quality_score"))


def test_demo_scorecard_values(demo_conn):
    card = quality.scorecard(demo_conn)
    # 285 rows in the CSV, all complete and valid; one verbatim copy.
    assert (dim(card, "completeness")["numerator"], dim(card, "completeness")["denominator"]) == (285, 285)
    assert (dim(card, "uniqueness")["numerator"], dim(card, "uniqueness")["denominator"]) == (284, 285)
    assert dim(card, "consistency")["value_pct"] == 100.0
    n = database.count_transactions(demo_conn)
    uncategorised = demo_conn.execute("SELECT COUNT(*) FROM transactions WHERE categorization_method='none'").fetchone()[0]
    assert dim(card, "categorisation")["numerator"] == n - uncategorised


def test_old_database_is_migrated(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript("""CREATE TABLE statements (id INTEGER PRIMARY KEY, display_name TEXT NOT NULL, file_hash TEXT UNIQUE,
        parser_name TEXT NOT NULL, statement_period_start TEXT, statement_period_end TEXT,
        processing_status TEXT NOT NULL DEFAULT 'imported', rows_extracted INTEGER NOT NULL DEFAULT 0,
        rows_imported INTEGER NOT NULL DEFAULT 0, rows_invalid INTEGER NOT NULL DEFAULT 0,
        rows_skipped_duplicates INTEGER NOT NULL DEFAULT 0, balance_checked_pairs INTEGER NOT NULL DEFAULT 0,
        balance_mismatches INTEGER NOT NULL DEFAULT 0, warnings TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL);
        INSERT INTO statements (display_name, parser_name, rows_extracted, created_at) VALUES ('legacy', 'x', 3, 'now');""")
    old.commit()
    old.close()
    conn = database.connect(path)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(statements)")}
    assert "quality_report" in cols
    card = quality.scorecard(conn)
    assert "older import" in dim(card, "completeness")["note"]


# ------------------------------------------------------------------- privacy

def test_report_contains_no_descriptions_or_identifiers():
    body = ("2026-01-01,UPI/DR/123456789012/RAHUL KUMAR/YESB/rahul.k@okhdfc/Payment,100.00,,900.00\n"
            "2026-01-02,,5.00,,895.00\n")
    r = quality.import_report(preview_csv(body))
    text = json.dumps(r)
    assert "RAHUL" not in text and "@" not in text and "123456789012" not in text


# ------------------------------------------------------------ parser evaluation

def test_parser_evaluation_on_synthetic_fixtures():
    results, summary = parser_eval.run_all(include_real=False)
    by = {r["fixture"]: r for r in results}
    assert set(by) == {"bank_single_page", "bank_multi_page", "bank_wrapped_description", "bank_with_refunds",
                       "phonepe_no_balance"}
    assert by["bank_multi_page"]["pages"] >= 2 and by["bank_multi_page"]["expected_rows"] == 140
    assert all(r["count_agreement"] and r["missed_rows"] == 0 for r in results)
    assert by["phonepe_no_balance"]["balance_reconciliation_pct"] is None
    assert summary["synthetic"]["expected_rows"] == 12 + 140 + 15 + 30 + 36
    assert summary["real"]["fixtures"] == 0 and summary["real"]["date_accuracy_pct"] is None


def test_parser_evaluator_detects_errors():
    """Tamper with the ground truth: the metrics must drop by exactly the tampered rows."""
    fx = next(f for f in parser_eval.synthetic_fixtures() if f.name == "bank_single_page")
    fx.expected[3].date = "2030-01-01"                       # wrong date on one row
    fx.expected[5].description = "SOMETHING ELSE ENTIRELY"   # wrong description on one row
    fx.expected.append(parser_eval.ExpectedRow("2026-07-31", "NEVER PRINTED", "debit", 1_00))  # missed row
    r = parser_eval.evaluate(fx)
    assert r["expected_rows"] == 13 and r["extracted_rows"] == 12 and r["count_agreement"] is False
    assert r["missed_rows"] == 1 and r["spurious_rows"] == 0
    assert r["date_accuracy_pct"] == round(100 * 11 / 13, 1)       # 13 expected − 1 wrong − 1 missed
    assert r["amount_accuracy_pct"] == round(100 * 12 / 13, 1)
    assert r["description_exact_pct"] == round(100 * 11 / 13, 1)


def test_jaccard():
    assert parser_eval.jaccard("UPI/DR/ZOMATO", "upi dr zomato") == 1.0
    assert parser_eval.jaccard("A B", "B C") == pytest.approx(1 / 3)


# ------------------------------------------------------------------------ API

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


def test_api_quality_scorecard_and_filters(client):
    j = client.get("/api/quality", headers=DEMO).json()
    keys = [d["key"] for d in j["scorecard"]["dimensions"]]
    assert keys == ["completeness", "validity", "uniqueness", "consistency", "categorisation", "reconciliation"]
    assert any(t["code"] == "ambiguous_date" for t in j["issue_types"])
    sid = j["all_statements"][0]["id"]
    assert client.get(f"/api/quality?statement_id={sid}", headers=DEMO).status_code == 200
    assert client.get("/api/quality?statement_id=9999", headers=DEMO).status_code == 404
    assert client.get("/api/quality?issue=nonsense", headers=DEMO).status_code == 400


def test_api_preview_carries_report_and_issue_filter(client):
    rows = _bank()
    rows[1]["debit"] = None
    rows[1]["balance"] = None
    pdf = bank_statement_pdf(rows)
    pre = client.post("/api/import/preview", headers=USER, files={"file": ("s.pdf", pdf, "application/pdf")}).json()
    assert pre["report"]["rejected_by_reason"]["missing_amount"] == 1
    assert pre["report"]["rows_extracted"] == 6 and pre["report"]["rows_accepted"] == 5
    client.post(f"/api/import/{pre['token']}/commit", json={}, headers=USER)
    j = client.get("/api/quality?issue=missing_amount", headers=USER).json()
    assert [i["code"] for i in j["issues"]] == ["missing_amount"]
    assert client.get("/api/quality?issue=invalid_date", headers=USER).json()["issues"] == []
