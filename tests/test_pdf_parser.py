import io
from datetime import date, timedelta

import pytest
from reportlab.pdfgen import canvas

from src import config, pipeline
from src.pdf_parser import (InvalidFileError, NoTextError, PasswordRequiredError, UnsupportedFormatError,
                            parse_statement, validate_upload)
from src.sample_pdfs import bank_statement_pdf, image_only_pdf, phonepe_statement_pdf, unrelated_text_pdf


def bank_rows(n: int, start=date(2026, 7, 1)):
    rows, balance = [], 100_000_00
    for i in range(n):
        amount = 100_00 + i * 10
        balance -= amount
        rows.append({"date": start + timedelta(days=i % 28), "description": f"UPI/DR/4123456789{i:02d}/ZOMATO/YESB",
                     "debit": amount, "credit": None, "balance": balance})
    return rows


def test_bank_table_single_page():
    pdf = bank_statement_pdf(bank_rows(5), period=(date(2026, 7, 1), date(2026, 7, 31)))
    result = parse_statement(pdf, "statement.pdf")
    assert result.parser_name == "bank_table"
    assert len(result.rows) == 5
    assert result.rows[0].debit_text == "100.00"
    assert (result.period_start, result.period_end) == ("2026-07-01", "2026-07-31")


def test_bank_table_multiple_pages_with_repeated_headers():
    pdf = bank_statement_pdf(bank_rows(120))
    result = parse_statement(pdf, "statement.pdf")
    assert result.page_count >= 2
    assert len(result.rows) == 120  # header rows on each page are not counted as transactions
    assert {r.page for r in result.rows} >= {1, 2}


def test_bank_table_end_to_end_balance_reconciles():
    preview = pipeline.prepare_pdf_import(bank_statement_pdf(bank_rows(30)), "s.pdf", conn=None)
    assert len(preview.rows) == 30 and not preview.invalid_rows
    assert preview.quality.balance_check.mismatches == 0


def test_wrapped_description_is_joined_to_previous_row():
    pdf = bank_statement_pdf(bank_rows(3), wrap_first_description=True)
    result = parse_statement(pdf, "s.pdf")
    assert len(result.rows) == 3
    assert "MONTHLY PAYMENT" in result.rows[0].description
    assert any("wrapped" in w for w in result.warnings)


def test_row_with_missing_amount_is_reported():
    rows = bank_rows(3)
    rows[1]["debit"] = None
    rows[1]["balance"] = None
    preview = pipeline.prepare_pdf_import(bank_statement_pdf(rows), "s.pdf", conn=None)
    assert len(preview.rows) == 2
    assert len(preview.invalid_rows) == 1 and "Amount: missing" in preview.invalid_rows[0]["reason"]


def test_phonepe_layout():
    rows = [{"date": date(2026, 9, 30 - i), "details": f"Paid to Zomato", "direction": "debit",
             "amount": 350_00 + i, "txn_id": f"T26093019{i:08d}"} for i in range(4)]
    rows.append({"date": date(2026, 9, 1), "details": "Received from Rohan Mehta", "direction": "credit",
                 "amount": 1_250_50, "txn_id": "T2609011234567890"})
    result = parse_statement(phonepe_statement_pdf(rows), "phonepe.pdf")
    assert result.parser_name == "phonepe"
    assert len(result.rows) == 5
    assert result.rows[-1].drcr_text.upper() == "CREDIT" and result.rows[-1].amount_text == "1,250.5"
    assert all(r.reference for r in result.rows)


def test_phonepe_overlapping_upload_is_exact_duplicate():
    from src import database
    conn = database.connect(":memory:")
    rows = [{"date": date(2026, 9, 10), "details": "Paid to Zomato", "direction": "debit",
             "amount": 350_00, "txn_id": "T2609101111111111"}]
    first = pipeline.prepare_pdf_import(phonepe_statement_pdf(rows), "a.pdf", conn)
    pipeline.commit_import(conn, first)
    # A different file (extra row) covering the same transaction:
    rows.append({"date": date(2026, 9, 11), "details": "Paid to Uber", "direction": "debit",
                 "amount": 210_00, "txn_id": "T2609112222222222"})
    second = pipeline.prepare_pdf_import(phonepe_statement_pdf(rows), "b.pdf", conn)
    statuses = sorted(r["duplicate_status"] for r in second.rows)
    assert statuses == ["exact_existing", "none"]


@pytest.mark.parametrize("filename, data, error", [
    ("statement.csv", b"%PDF-1.4 fake", InvalidFileError),
    ("statement.pdf", b"", InvalidFileError),
    ("statement.pdf", b"hello, I am not a pdf", InvalidFileError),
    ("statement.pdf", b"%PDF-1.4\n garbage garbage", InvalidFileError),
])
def test_invalid_files_are_rejected(filename, data, error):
    with pytest.raises(error):
        parse_statement(data, filename)


def test_file_size_limit(monkeypatch):
    big = b"%PDF-1.4" + b"0" * (config.UPLOAD.max_file_size_bytes + 1)
    with pytest.raises(InvalidFileError, match="larger than"):
        validate_upload("big.pdf", big)


def test_scanned_pdf_without_text():
    with pytest.raises(NoTextError, match="OCR"):
        parse_statement(image_only_pdf(), "scan.pdf")


def test_unsupported_layout_gives_helpful_error():
    with pytest.raises(UnsupportedFormatError, match="Supported formats"):
        parse_statement(unrelated_text_pdf(), "notes.pdf")


def test_password_protected_pdf():
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, encrypt="secret123")
    c.drawString(50, 750, "Locked statement for a demo account, nothing else here")
    c.save()
    with pytest.raises(PasswordRequiredError):
        parse_statement(buffer.getvalue(), "locked.pdf")
    # With the right password the file opens (and then fails only because the layout is unknown).
    with pytest.raises(UnsupportedFormatError):
        parse_statement(buffer.getvalue(), "locked.pdf", password="secret123")


def test_bundled_sample_pdfs_parse():
    for name, parser in [("sample_bank_statement.pdf", "bank_table"), ("sample_phonepe_statement.pdf", "phonepe")]:
        data = (config.PROJECT_ROOT / "data" / "sample_statements" / name).read_bytes()
        preview = pipeline.prepare_pdf_import(data, name, conn=None)
        assert preview.parser_name == parser
        assert len(preview.rows) > 20 and not preview.invalid_rows
