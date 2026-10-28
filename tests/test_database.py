import sqlite3

import pytest

from src import config, database, pipeline
from tests.conftest import SMALL_CSV


def test_schema_initialisation(empty_conn):
    tables = {r[0] for r in empty_conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"transactions", "statements", "categories", "import_issues", "recurring_decisions",
            "anomaly_reviews", "manual_corrections"} <= tables
    cats = [r[0] for r in empty_conn.execute("SELECT category_name FROM categories")]
    assert set(cats) == set(config.CATEGORIES)
    # Re-initialising is harmless.
    database.init_db(empty_conn)
    assert empty_conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == len(config.CATEGORIES)


def test_import_and_statement_record(small_conn):
    assert database.count_transactions(small_conn) == 9
    statement = database.list_statements(small_conn)[0]
    assert statement["rows_imported"] == 9 and statement["parser_name"] == "sample_csv"


def test_same_file_cannot_be_imported_twice(small_conn):
    preview = pipeline.prepare_csv_rows_import(SMALL_CSV, display_name="again", conn=small_conn)
    assert preview.already_imported
    with pytest.raises(ValueError):
        pipeline.commit_import(small_conn, preview)
    assert database.count_transactions(small_conn) == 9


def test_import_is_atomic(empty_conn):
    preview = pipeline.prepare_csv_rows_import(SMALL_CSV, display_name="x", conn=empty_conn)
    preview.rows[3]["category"] = "Not a real category"  # violates the foreign key
    with pytest.raises(sqlite3.IntegrityError):
        pipeline.commit_import(empty_conn, preview)
    assert database.count_transactions(empty_conn) == 0
    assert database.list_statements(empty_conn) == []


def test_constraints_reject_bad_values(small_conn):
    with pytest.raises(sqlite3.IntegrityError):
        small_conn.execute("UPDATE transactions SET amount_paise = -5 WHERE id = 1")
    with pytest.raises(sqlite3.IntegrityError):
        small_conn.execute("UPDATE transactions SET direction = 'sideways' WHERE id = 1")


def test_manual_update_is_logged(small_conn):
    txn_id = small_conn.execute(
        "SELECT id FROM transactions WHERE normalized_merchant = 'Rohan Mehta'").fetchone()[0]
    database.update_transaction_fields(small_conn, txn_id, {"category": "Income", "transaction_type": "income"})
    row = database.get_transaction(small_conn, txn_id)
    assert (row["category"], row["transaction_type"], row["categorization_method"], row["review_status"]) == \
        ("Income", "income", "manual", "reviewed")
    log = small_conn.execute("SELECT field, old_value, new_value FROM manual_corrections").fetchall()
    assert ("category", "Other", "Income") in [tuple(r) for r in log]


def test_update_rejects_non_editable_columns(small_conn):
    with pytest.raises(ValueError):
        database.update_transaction_fields(small_conn, 1, {"amount_paise": 1})


def test_parameterized_queries_treat_input_as_data(small_conn):
    evil = "x'; DROP TABLE transactions; --"
    database.set_recurring_decision(small_conn, evil, "rejected")
    assert database.recurring_decisions(small_conn)[evil] == "rejected"
    assert database.count_transactions(small_conn) == 9


def test_clear_all_data(small_conn):
    database.set_recurring_decision(small_conn, "Netflix", "confirmed")
    database.clear_all_data(small_conn)
    assert database.count_transactions(small_conn) == 0
    assert database.list_statements(small_conn) == []
    assert database.recurring_decisions(small_conn) == {}


def test_demo_and_user_databases_are_separate_files(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    assert config.db_path("demo") != config.db_path("user")
    with pytest.raises(ValueError):
        config.db_path("everything")


def test_coverage_period(small_conn):
    assert database.coverage_period(small_conn) == ("2026-01-01", "2026-03-05")
