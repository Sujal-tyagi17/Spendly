"""Rules learned from the user's own fixes, balance-mismatch review flags, and
uncategorised counts that ignore skipped duplicates. Synthetic data only."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from api import main
from api.state import ConnectionManager, PreviewStore
from src import config, database, pipeline, quality
from src.sample_pdfs import bank_statement_pdf
from tests.conftest import rows_to_csv

USER = {"X-Spendly-Mode": "user"}

FRIEND_OCT = rows_to_csv([
    ("2026-10-01", "UPI/CR/100000000001/ROHAN MEHTA/HDFC/rohan@okaxis/Payment", None, "1500.00"),
    ("2026-10-02", "UPI/DR/100000000002/VERMA GENERAL STORE/YESB", "845.00", None),
    ("2026-10-03", "UPI/DR/100000000003/ZOMATO/YESB/zomato@ybl/Payment", "450.00", None),
])
FRIEND_NOV = rows_to_csv([
    ("2026-11-01", "UPI/CR/200000000001/ROHAN MEHTA/HDFC/rohan@okaxis/Payment", None, "700.00"),
    ("2026-11-02", "UPI/DR/200000000002/ROHAN MEHTA/HDFC/rohan@okaxis/Payment", "300.00", None),
    ("2026-11-04", "UPI/DR/200000000003/VERMA GENERAL STORE/YESB", "120.00", None),
    ("2026-11-05", "NEFT/CR/200000000004/ACME TECH/SALARY NOV", None, "85000.00"),
])


def _import(conn, text, name):
    preview = pipeline.prepare_csv_rows_import(text, display_name=name, conn=conn)
    pipeline.commit_import(conn, preview)
    return preview


def _row(conn, merchant, direction, date_prefix):
    return dict(conn.execute(
        "SELECT * FROM transactions WHERE normalized_merchant = ? AND direction = ? AND transaction_date LIKE ?",
        (merchant, direction, date_prefix + "%")).fetchone())


@pytest.fixture
def conn():
    c = database.connect(":memory:")
    yield c
    c.close()


# ------------------------------------------------------------ merchant rules

def test_a_fix_becomes_a_rule_and_applies_to_the_next_import(conn):
    _import(conn, FRIEND_OCT, "oct")
    rohan = _row(conn, "Rohan Mehta", "credit", "2026-10")
    verma = _row(conn, "Verma General Store", "debit", "2026-10")
    assert rohan["categorization_method"] == "none" and verma["categorization_method"] == "none"

    database.update_transaction_fields(conn, rohan["id"], {"category": "Income", "transaction_type": "income"})
    database.update_transaction_fields(conn, verma["id"], {"category": "Groceries"})
    assert database.merchant_rules(conn) == {
        ("Rohan Mehta", "credit"): ("Income", "income"),
        ("Verma General Store", "debit"): ("Groceries", "expense"),
    }

    preview = _import(conn, FRIEND_NOV, "nov")
    assert preview.from_your_rules == 2 and preview.uncategorized == 1  # only the debit to Rohan is new

    new_rohan = _row(conn, "Rohan Mehta", "credit", "2026-11")
    assert (new_rohan["category"], new_rohan["transaction_type"], new_rohan["categorization_method"],
            new_rohan["review_status"]) == ("Income", "income", "user_rule", "ok")
    assert _row(conn, "Verma General Store", "debit", "2026-11")["category"] == "Groceries"
    # A rule is per direction: paying Rohan is not income.
    assert _row(conn, "Rohan Mehta", "debit", "2026-11")["categorization_method"] == "none"


def test_structural_rules_always_beat_your_rules(conn):
    _import(conn, FRIEND_NOV, "nov")
    salary = _row(conn, "Acme Tech", "credit", "2026-11")
    assert salary["categorization_method"] == "rule"
    database.save_merchant_rule(conn, "Acme Tech", "credit", "Refunds", "refund")
    again = pipeline.prepare_csv_rows_import(FRIEND_NOV.replace("SALARY NOV", "SALARY DEC")
                                             .replace("2026-11", "2026-12"), display_name="dec", conn=conn)
    row = next(r for r in again.rows if r["normalized_merchant"] == "Acme Tech")
    assert (row["transaction_type"], row["categorization_method"]) == ("income", "rule")


def test_your_rule_beats_a_builtin_merchant_match(conn):
    _import(conn, FRIEND_OCT, "oct")
    zomato = _row(conn, "Zomato", "debit", "2026-10")
    assert zomato["categorization_method"] == "merchant"
    database.update_transaction_fields(conn, zomato["id"], {"category": "Entertainment"})
    preview = pipeline.prepare_csv_rows_import(
        rows_to_csv([("2026-11-09", "UPI/DR/300000000001/ZOMATO/YESB/zomato@ybl/Payment", "99.00", None)]),
        display_name="x", conn=conn)
    assert (preview.rows[0]["category"], preview.rows[0]["categorization_method"]) == ("Entertainment", "user_rule")


def test_setting_other_removes_the_rule_instead_of_saving_it(conn):
    _import(conn, FRIEND_OCT, "oct")
    verma = _row(conn, "Verma General Store", "debit", "2026-10")
    database.update_transaction_fields(conn, verma["id"], {"category": "Groceries"})
    assert ("Verma General Store", "debit") in database.merchant_rules(conn)
    database.update_transaction_fields(conn, verma["id"], {"category": config.UNCATEGORIZED})
    assert ("Verma General Store", "debit") not in database.merchant_rules(conn)


def test_rules_are_listed_deleted_and_cleared_with_the_data(conn):
    _import(conn, FRIEND_OCT, "oct")
    database.update_transaction_fields(conn, _row(conn, "Verma General Store", "debit", "2026-10")["id"],
                                       {"category": "Groceries"})
    rules = database.list_merchant_rules(conn)
    assert [(r["merchant"], r["category"], r["transactions"]) for r in rules] == [("Verma General Store", "Groceries", 1)]
    assert database.delete_merchant_rule(conn, rules[0]["id"]) is True
    assert database.delete_merchant_rule(conn, rules[0]["id"]) is False
    # Forgetting a rule keeps the category already set on saved rows.
    assert _row(conn, "Verma General Store", "debit", "2026-10")["category"] == "Groceries"

    database.save_merchant_rule(conn, "Verma General Store", "debit", "Groceries", "expense")
    database.clear_all_data(conn)
    assert database.merchant_rules(conn) == {}


def test_scorecard_reports_rows_categorised_from_your_rules(conn):
    _import(conn, FRIEND_OCT, "oct")
    database.update_transaction_fields(conn, _row(conn, "Rohan Mehta", "credit", "2026-10")["id"],
                                       {"category": "Income", "transaction_type": "income"})
    _import(conn, FRIEND_NOV, "nov")
    card = quality.scorecard(conn)
    assert card["categorisation_methods"]["user_rule"] == 1
    note = next(d for d in card["dimensions"] if d["key"] == "categorisation")["note"]
    assert note.startswith("1 row categorised from your rules")


def test_older_databases_turn_existing_fixes_into_rules_once(tmp_path):
    path = tmp_path / "old.db"
    c = database.connect(path)
    _import(c, FRIEND_OCT, "oct")
    rohan = _row(c, "Rohan Mehta", "credit", "2026-10")
    # Simulate a database from before rules existed: a manual fix, no rule, migration not yet run.
    c.execute("UPDATE transactions SET category = 'Income', transaction_type = 'income', "
              "categorization_method = 'manual' WHERE id = ?", (rohan["id"],))
    c.execute("DELETE FROM merchant_rules")
    c.execute("DELETE FROM schema_meta WHERE key = 'merchant_rules_from_corrections_v1'")
    c.close()

    c = database.connect(path)
    assert database.merchant_rules(c) == {("Rohan Mehta", "credit"): ("Income", "income")}
    database.delete_merchant_rule(c, database.list_merchant_rules(c)[0]["id"])
    c.close()
    c = database.connect(path)  # runs once only: a forgotten rule doesn't come back
    assert database.merchant_rules(c) == {}
    c.close()


# --------------------------------------------- balance mismatches need review

def _statement_with_misprint():
    rows, bal = [], 10_000_00
    for i, amount in enumerate([100_00, 200_00, 300_00, 400_00]):
        bal -= amount
        rows.append({"date": date(2026, 12, 1 + i), "description": f"UPI/DR/90000000000{i}/ZOMATO/YESB",
                     "debit": amount, "credit": None, "balance": bal})
    rows[2]["balance"] += 50_00
    return bank_statement_pdf(rows, period=(date(2026, 12, 1), date(2026, 12, 31)))


def test_balance_mismatch_rows_are_put_under_needs_review(conn):
    preview = pipeline.prepare_pdf_import(_statement_with_misprint(), "dec.pdf", conn)
    flagged = [r for r in preview.rows if r["balance_check"] == "mismatch"]
    assert len(flagged) == 2
    assert all(r["review_status"] == "needs_review" and r["review_reason"] == database.BALANCE_MISMATCH_REASON
               for r in flagged)
    assert all(r["review_status"] == "ok" for r in preview.rows if r["balance_check"] != "mismatch")


def test_older_databases_flag_existing_mismatch_rows_once(tmp_path):
    path = tmp_path / "old.db"
    c = database.connect(path)
    pipeline.commit_import(c, pipeline.prepare_pdf_import(_statement_with_misprint(), "dec.pdf", c))
    c.execute("UPDATE transactions SET review_status = 'ok', review_reason = NULL")
    c.execute("DELETE FROM schema_meta WHERE key = 'flag_balance_mismatches_v1'")
    c.close()
    c = database.connect(path)
    statuses = dict(c.execute("SELECT balance_check, review_status FROM transactions "
                              "WHERE balance_check = 'mismatch'").fetchall())
    assert statuses == {"mismatch": "needs_review"}
    c.execute("UPDATE transactions SET review_status = 'reviewed' WHERE balance_check = 'mismatch'")
    c.close()
    c = database.connect(path)  # a row you reviewed isn't flagged again
    assert c.execute("SELECT COUNT(*) FROM transactions WHERE review_status = 'needs_review'").fetchone()[0] == 0
    c.close()


# ------------------------------------- skipped duplicates aren't "uncategorised"

def test_uncategorised_count_ignores_skipped_exact_duplicates(conn):
    rows, bal = [], 5_000_00
    for i, desc in enumerate(["UPI/DR/700000000001/GUPTA AUTO PARTS/YESB", "UPI/DR/700000000002/ZOMATO/YESB"]):
        bal -= 100_00
        rows.append({"date": date(2026, 12, 2 + i), "description": desc, "debit": 100_00, "credit": None, "balance": bal})
    rows.insert(1, dict(rows[0]))  # the same Gupta row printed twice
    preview = pipeline.prepare_pdf_import(bank_statement_pdf(rows), "dup.pdf", conn)
    assert preview.exact_duplicates == 1
    assert preview.uncategorized == 1
    report = quality.import_report(preview)
    assert report["flags"]["uncategorised"] == 1
    assert report["dimensions"]["categorisation_coverage_pct"] == 50.0
    # If the user chooses to import the copy too, it is counted.
    assert quality.import_report(preview, include_exact_duplicates=True)["flags"]["uncategorised"] == 2


# ---------------------------------------------------------------------- API

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "connections", ConnectionManager(public=False))
    monkeypatch.setattr(main, "previews", PreviewStore())
    with TestClient(main.app) as c:
        yield c
    main.connections.close_all()


def test_rules_api_round_trip(client):
    preview = client.post("/api/import/preview", headers=USER,
                          files={"file": ("dec.pdf", _statement_with_misprint(), "application/pdf")}).json()
    assert preview["counts"]["from_your_rules"] == 0
    client.post(f"/api/import/{preview['token']}/commit", headers=USER, json={})
    txn = client.get("/api/transactions", headers=USER).json()["rows"][0]
    assert client.patch(f"/api/transactions/{txn['id']}", headers=USER, json={"category": "Shopping"}).status_code == 200

    rules = client.get("/api/rules", headers=USER).json()["rules"]
    assert [(r["merchant"], r["direction"], r["category"]) for r in rules] == [("Zomato", "debit", "Shopping")]
    assert client.delete(f"/api/rules/{rules[0]['id']}", headers=USER).json() == {"deleted": 1}
    assert client.delete(f"/api/rules/{rules[0]['id']}", headers=USER).status_code == 404
    assert client.get("/api/rules", headers=USER).json()["rules"] == []


# ------------------------------------------- gaps between statements aren't zero

def test_a_gap_between_statements_is_not_compared_as_zero(conn):
    from src import insights, kpis
    oct_rows = rows_to_csv([("2026-10-03", "UPI/DR/1/ZOMATO/YESB", "500.00", None)])
    jan_rows = rows_to_csv([("2027-01-09", "UPI/DR/2/ZOMATO/YESB", "800.00", None)])
    pipeline.commit_import(conn, pipeline.prepare_csv_rows_import(
        oct_rows, display_name="oct", conn=conn, period=("2026-10-01", "2026-10-31")))
    pipeline.commit_import(conn, pipeline.prepare_csv_rows_import(
        jan_rows, display_name="jan", conn=conn, period=("2027-01-01", "2027-01-31")))

    assert insights.compare_periods(conn) is None
    assert insights.uncovered_previous_month(conn) == "December 2026"
    story = kpis.explain_change(conn)
    assert story["available"] is False
    assert "No imported statement covers December 2026" in story["caveats"][0]
    # No "biggest increase" cards built against a missing month.
    keys = {i.key for i in insights.build_insights(conn, None, [], None)}
    assert not keys & {"biggest_increase", "biggest_decrease", "overall_change"}
