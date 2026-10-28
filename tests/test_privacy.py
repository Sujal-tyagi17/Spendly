import logging
from datetime import date

import pytest

from src import ai, config, database, pipeline
from src.privacy import mask_sensitive, sanitize_for_ai
from src.sample_pdfs import bank_statement_pdf


def test_mask_sensitive():
    text = "UPI/DR/412345678901/ZOMATO/YESB/zomato@ybl call 9876543210 acct 123456789012345"
    masked = mask_sensitive(text)
    assert "412345678901" not in masked and "XXXX8901" in masked
    assert "zomato@ybl" not in masked and "[upi-id]" in masked
    assert "9876543210" not in masked and "[phone]" in masked
    assert "123456789012345" not in masked
    assert "ZOMATO" in masked  # still readable


def test_sanitize_for_ai_removes_identifiers():
    assert sanitize_for_ai("UPI/DR/412345678901/SHARMA STORE/sharma@okaxis XXXX1234") == "UPI DR SHARMA STORE"


def test_descriptions_are_masked_before_storage(small_conn):
    descriptions = [r[0] for r in small_conn.execute("SELECT description FROM transactions")]
    assert all("111111111111" not in d for d in descriptions)
    assert all("@" not in d for d in descriptions)


def test_uploaded_pdf_is_not_written_to_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.chdir(tmp_path)
    conn = database.connect(tmp_path / "spendly_user.db")
    rows = [{"date": date(2026, 7, 1), "description": "UPI/DR/412345678901/ZOMATO", "debit": 350_00,
             "credit": None, "balance": 9_650_00}]
    preview = pipeline.prepare_pdf_import(bank_statement_pdf(rows), "my statement.pdf", conn)
    pipeline.commit_import(conn, preview)
    files = {p.name for p in tmp_path.rglob("*")}
    assert not any(name.endswith(".pdf") for name in files)
    assert files <= {"spendly_user.db", "spendly_user.db-journal"}


def test_logs_contain_no_transaction_descriptions(caplog):
    caplog.set_level(logging.DEBUG)
    rows = [{"date": date(2026, 7, 1), "description": "UPI/DR/412345678901/SECRET MERCHANT/x@ybl",
             "debit": 350_00, "credit": None, "balance": 9_650_00}]
    preview = pipeline.prepare_pdf_import(bank_statement_pdf(rows), "statement.pdf", conn=None)
    conn = database.connect(":memory:")
    pipeline.commit_import(conn, preview)
    assert caplog.records, "expected some log output"
    log_text = " ".join(r.getMessage() for r in caplog.records)
    assert "SECRET MERCHANT" not in log_text
    assert "412345678901" not in log_text


def test_ai_disabled_without_key(monkeypatch):
    monkeypatch.setenv("SPENDLY_ENABLE_AI", "true")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    enabled, message = ai.ai_status()
    assert not enabled and "GEMINI_API_KEY" in message
    with pytest.raises(ai.AIError):
        ai.suggest_categories(["Green Leaf Salon"])


def test_ai_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SPENDLY_ENABLE_AI", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    assert ai.ai_status()[0] is False


def test_ai_payload_preview_has_no_identifiers():
    payload = ai.preview_payload(["Sharma Store", "UPI/412345678901/x@ybl", "Sharma Store"])
    assert payload == ["Sharma Store", "UPI"]


def test_ai_output_validation(monkeypatch):
    monkeypatch.setenv("SPENDLY_ENABLE_AI", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.setattr(ai, "_generate", lambda prompt: '{"Green Leaf Salon": "Shopping", "Odd Shop": "Gambling"}')
    assert ai.suggest_categories(["Green Leaf Salon", "Odd Shop"]) == {"Green Leaf Salon": "Shopping"}


def test_ai_rephrase_rejects_invented_numbers(monkeypatch):
    monkeypatch.setenv("SPENDLY_ENABLE_AI", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    facts = ["Your expenditure increased by 18.0% (₹10,000 → ₹11,800)."]
    monkeypatch.setattr(ai, "_generate", lambda p: '{"summary": "Spending rose 18.0% to ₹11,800."}')
    assert ai.rephrase_insights(facts) == "Spending rose 18.0% to ₹11,800."
    monkeypatch.setattr(ai, "_generate", lambda p: '{"summary": "Spending rose about 20% to ₹12,000."}')
    assert ai.rephrase_insights(facts) is None
