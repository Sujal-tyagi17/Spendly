"""QA: parser edge cases, normalisation invariants, API behaviour, database integrity,
privacy, and regression tests for the defects found in the end-to-end audit (QA-1 … QA-5)."""

import csv
import io
import logging
import threading
from datetime import date

import pytest
from fastapi.testclient import TestClient
from reportlab.lib import pdfencrypt
from reportlab.pdfgen import canvas

from api import main
from api.state import ConnectionManager, PreviewStore
from src import analytics, config, database, pipeline
from src.merchant_normalizer import normalize_merchant
from src.money import AmountParseError, format_inr, parse_amount
from src.pdf_parser import EmptyStatementError, InvalidFileError, PasswordRequiredError, parse_statement
from src.sample_pdfs import bank_statement_pdf, phonepe_statement_pdf
from src.transaction_normalizer import DateParseError, parse_date

DEMO = {"X-Spendly-Mode": "demo"}
USER = {"X-Spendly-Mode": "user"}


def bank_rows(n, start=date(2026, 7, 1), amount=100_00, desc="UPI/DR/4{i:05d}/ZOMATO/YESB"):
    rows, bal = [], 1_00_000_00
    for i in range(n):
        bal -= amount
        rows.append({"date": date(start.year, start.month, 1 + i % 28), "description": desc.format(i=i),
                     "debit": amount, "credit": None, "balance": bal})
    return rows


def locked_pdf(password="secret123") -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, encrypt=pdfencrypt.StandardEncryption(password, canPrint=0))
    c.drawString(50, 750, "locked")
    c.save()
    return buf.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "connections", ConnectionManager(public=False))
    monkeypatch.setattr(main, "previews", PreviewStore())
    with TestClient(main.app, raise_server_exceptions=False) as c:
        yield c
    main.connections.close_all()


def upload(client, pdf, name="s.pdf", **data):
    return client.post("/api/import/preview", headers=USER, files={"file": (name, pdf, "application/pdf")}, data=data)


# --------------------------------------------------------------- regressions

def test_qa1_empty_supported_statement_says_so():
    """QA-1: a recognised layout with zero rows used to say "layout not supported"."""
    with pytest.raises(EmptyStatementError, match="no transaction rows"):
        parse_statement(bank_statement_pdf([]), "s.pdf")


def test_qa2_single_row_with_balance_is_not_reported_as_no_balance_column():
    """QA-2: one row with a balance was reported as "no balance column"."""
    p = pipeline.prepare_pdf_import(bank_statement_pdf(bank_rows(1)), "s.pdf", conn=None)
    assert len(p.rows) == 1
    assert not any("No balance column" in w for w in p.warnings)
    assert any("at least two consecutive rows" in w for w in p.warnings)
    from src import quality
    assert "no_balance_column" not in {i["code"] for i in quality.import_report(p)["issues"]}
    pp = [{"date": date(2026, 8, 1), "details": "Paid to Zomato", "direction": "debit", "amount": 100_00, "txn_id": "T1"}]
    p2 = pipeline.prepare_pdf_import(phonepe_statement_pdf(pp), "p.pdf", conn=None)
    assert "no_balance_column" in {i["code"] for i in quality.import_report(p2)["issues"]}


def test_qa3_csv_export_neutralises_formulas(client):
    """QA-3: statement text starting with = + - @ was exported verbatim (CSV formula injection)."""
    rows = bank_rows(3)
    rows[0]["description"] = "=HYPERLINK(\"http://x\",\"pay\")"
    rows[1]["description"] = "@SUM(A1:A2) SHOP"
    tok = upload(client, bank_statement_pdf(rows)).json()["token"]
    client.post(f"/api/import/{tok}/commit", json={}, headers=USER)
    text = client.get("/api/transactions/export.csv", headers=USER).text
    cells = [c for row in csv.reader(io.StringIO(text)) for c in row]
    assert not any(c[:1] in {"=", "+", "@"} for c in cells)
    assert any(c.startswith("'=HYPERLINK") for c in cells)
    amounts = [row["amount_inr"] for row in csv.DictReader(io.StringIO(text))]
    assert amounts == ["100.0", "100.0", "100.0"]


def test_qa4_bulk_category_change_is_atomic(client, monkeypatch):
    """QA-4: a failure half-way through a merchant-wide change left some rows changed."""
    tx = client.get("/api/transactions?merchants=Zomato&page_size=250", headers=DEMO).json()
    first = tx["rows"][0]
    original = {r["id"]: r["category"] for r in tx["rows"]}
    real = database.update_transaction_fields
    calls = {"n": 0}

    def flaky(conn, tid, changes):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("disk full")
        return real(conn, tid, changes)

    monkeypatch.setattr(database, "update_transaction_fields", flaky)
    r = client.patch(f"/api/transactions/{first['id']}", headers=DEMO,
                     json={"category": "Travel", "apply_to_merchant": True, "expected_count": tx["total"]})
    assert r.status_code == 500 and "disk full" not in r.text
    monkeypatch.setattr(database, "update_transaction_fields", real)
    after = client.get("/api/transactions?merchants=Zomato&page_size=250", headers=DEMO).json()["rows"]
    assert {r["id"]: r["category"] for r in after} == original


def test_qa5_wrong_password_message():
    """QA-5: a wrong password got the same message as a missing one."""
    with pytest.raises(PasswordRequiredError, match="didn't open"):
        parse_statement(locked_pdf(), "l.pdf", password="wrong")
    with pytest.raises(PasswordRequiredError, match="password-protected"):
        parse_statement(locked_pdf(), "l.pdf")


# ------------------------------------------------------------- PDF parsing

@pytest.mark.parametrize("name,data,err", [
    ("s.pdf", b"", InvalidFileError),
    ("s.txt", b"%PDF-1.4", InvalidFileError),
    ("s.pdf", b"hello world", InvalidFileError),
    ("s.pdf", b"%PDF-1.4\n%garbage\x00\x01", InvalidFileError),
])
def test_bad_files_fail_safely(name, data, err):
    with pytest.raises(err):
        parse_statement(data, name)


def test_uppercase_extension_and_one_row():
    p = pipeline.prepare_pdf_import(bank_statement_pdf(bank_rows(1)), "STATEMENT.PDF", conn=None)
    assert [(r["transaction_date"], r["amount_paise"], r["direction"]) for r in p.rows] == [("2026-07-01", 10000, "debit")]


def test_punctuation_and_numbers_in_descriptions():
    rows = bank_rows(2)
    rows[0]["description"] = "POS/XXXX1111/DOMINO'S PIZZA #1234, M.G. ROAD (BLR) & CO."
    p = pipeline.prepare_pdf_import(bank_statement_pdf(rows), "s.pdf", conn=None)
    assert p.rows[0]["description"] == "POS/XXXX1111/DOMINO'S PIZZA #1234, M.G. ROAD (BLR) & CO."
    assert p.rows[0]["normalized_merchant"] == "Domino's"


def test_many_rows_multipage_with_credits():
    rows = bank_rows(260)
    for i in range(0, 260, 13):
        rows[i]["credit"], rows[i]["debit"] = rows[i]["debit"], None
    bal = 1_00_000_00
    for r in rows:
        bal += r["credit"] or 0
        bal -= r["debit"] or 0
        r["balance"] = bal
    p = pipeline.prepare_pdf_import(bank_statement_pdf(rows), "s.pdf", conn=None)
    assert len(p.rows) == 260 and p.quality.balance_check.mismatches == 0
    assert sum(r["direction"] == "credit" for r in p.rows) == 20


# --------------------------------------------------------- money and dates

@pytest.mark.parametrize("text,paise", [("10,00,00,000.00", 10_00_00_000_00), ("1.5", 150), ("00.10", 10),
                                        ("₹ 1,234.5", 1_234_50), ("(1,000.00)", 1_000_00)])
def test_amounts_to_paise(text, paise):
    assert parse_amount(text)[0] == paise


@pytest.mark.parametrize("bad", ["0.005", "12.345", "1e3", "", "abc"])
def test_amounts_never_rounded_silently(bad):
    with pytest.raises(AmountParseError):
        parse_amount(bad)


def test_aggregation_is_exact_in_paise():
    # 0.1 + 0.2 ≠ 0.3 in floating point; in paise it's exact.
    rows = [("2026-01-01", f"UPI/DR/{i}/ZOMATO/YESB", amt, None) for i, amt in enumerate(["0.10", "0.20"] * 500)]
    from tests.test_advanced_analytics import make_conn
    c = make_conn(rows, [("2026-01-01", "2026-01-31")])
    assert analytics.totals(c)["expenditure_paise"] == 150_00
    assert format_inr(150_00, decimals=True) == "₹150.00"


@pytest.mark.parametrize("text,iso", [("29/02/2024", "2024-02-29"), ("31/12/2025", "2025-12-31"),
                                      ("01/01/2026", "2026-01-01"), ("Feb 29, 2024", "2024-02-29")])
def test_valid_boundary_dates(text, iso):
    assert parse_date(text).isoformat() == iso


@pytest.mark.parametrize("text", ["29/02/2025", "31-04-2026", "2026-02-30", "", None])
def test_invalid_dates_rejected(text):
    with pytest.raises(DateParseError):
        parse_date(text)


def test_ambiguous_date_refused_when_both_orders_allowed():
    with pytest.raises(DateParseError, match="ambiguous"):
        parse_date("04/05/2026", ("%d/%m/%Y", "%m/%d/%Y"))
    assert parse_date("13/05/2026", ("%d/%m/%Y", "%m/%d/%Y")).isoformat() == "2026-05-13"


# ------------------------------------------------------- normalisation

@pytest.mark.parametrize("a,b", [
    ("UPI/DR/1/ZOMATO/YESB", "upi/dr/2/zomato ltd/axis"),
    ("POS/XXXX1111/AMZN MKTPLACE", "POS/XXXX9999/AMAZON PAY INDIA"),
    ("  UPI/DR/3/SWIGGY/YESB  ", "UPI/DR/4/SWIGGY   /HDFC"),
])
def test_aliases_and_spelling_variants_merge(a, b):
    assert normalize_merchant(a).merchant == normalize_merchant(b).merchant


def test_distinct_merchants_are_not_merged():
    names = {normalize_merchant(d).merchant for d in ["UPI/DR/1/ZOMATO/YESB", "UPI/DR/1/SWIGGY/YESB",
                                                      "UPI/DR/1/SHARMA STORES/YESB", "UPI/DR/1/VERMA STORES/YESB"]}
    assert len(names) == 4


@pytest.mark.parametrize("desc", ["UPI/DR/1/ZOMATO/YESB", "UPI/DR/2/SHARMA STORES/YESB", "ACH/DR/3/NETFLIX.COM",
                                  "IMPS/DR/4/HOUSE RENT/MR K NAIR", "UPI/CR/5/ROHAN MEHTA/HDFC"])
def test_normalisation_is_idempotent(desc):
    once = normalize_merchant(desc).merchant
    assert normalize_merchant(once).merchant == once


# --------------------------------------------------------- import workflow

def test_full_import_workflow(client):
    rows = bank_rows(6)
    pdf = bank_statement_pdf(rows)
    pre = upload(client, pdf).json()
    assert pre["counts"]["to_import"] == 6
    assert [(r["date"], r["amount_paise"], r["direction"]) for r in pre["rows"]] == \
           [(r["date"].isoformat(), r["debit"], "debit") for r in rows]
    assert client.get("/api/meta", headers=USER).json()["counts"]["transactions"] == 0   # preview persists nothing
    done = client.post(f"/api/import/{pre['token']}/commit", json={}, headers=USER).json()
    assert done["imported"] == 6
    assert client.get("/api/overview", headers=USER).json()["totals"]["expenditure_paise"] == 600_00
    again = upload(client, pdf).json()
    assert again["already_imported"] is True
    assert client.post(f"/api/import/{again['token']}/commit", json={}, headers=USER).status_code == 409
    assert client.get("/api/overview", headers=USER).json()["totals"]["expenditure_paise"] == 600_00
    assert client.request("DELETE", "/api/data", json={"confirm": "DELETE"}, headers=USER).status_code == 200
    assert client.get("/api/overview", headers=USER).json()["totals"]["expenditure_paise"] == 0


def test_cancel_between_preview_and_commit(client):
    tok = upload(client, bank_statement_pdf(bank_rows(3))).json()["token"]
    assert client.delete(f"/api/import/{tok}", headers=USER).status_code == 200
    assert client.post(f"/api/import/{tok}/commit", json={}, headers=USER).status_code == 404
    assert client.get("/api/meta", headers=USER).json()["counts"]["transactions"] == 0


def test_commit_ignores_client_supplied_values(client):
    tok = upload(client, bank_statement_pdf(bank_rows(3))).json()["token"]
    r = client.post(f"/api/import/{tok}/commit", headers=USER,
                    json={"rows": [{"amount_paise": 999999999}], "total": 1, "category": "Income"})
    assert r.status_code == 200 and r.json()["imported"] == 3
    assert client.get("/api/overview", headers=USER).json()["totals"]["expenditure_paise"] == 300_00


def test_failed_imports_leave_nothing_behind(client):
    for pdf, kwargs in [(locked_pdf(), {"password": "wrong"}), (b"%PDF-1.4 broken", {}), (b"not a pdf", {})]:
        assert upload(client, pdf, **kwargs).status_code in {401, 422}
    assert client.post("/api/import/preview", headers=USER,
                       files={"file": ("x.csv", b"a,b", "text/csv")}).status_code == 422
    meta = client.get("/api/meta", headers=USER).json()
    assert meta["counts"] == {"transactions": 0, "statements": 0}


def test_oversized_upload_rejected(client, monkeypatch):
    monkeypatch.setattr(config, "UPLOAD", config.UploadSettings(max_file_size_mb=1))
    big = b"%PDF-1.4\n" + b"0" * (1024 * 1024 + 10)
    r = upload(client, big)
    assert r.status_code == 413


def test_interrupted_commit_rolls_back(monkeypatch):
    conn = database.connect(":memory:")
    preview = pipeline.prepare_pdf_import(bank_statement_pdf(bank_rows(4)), "s.pdf", conn=conn)

    def boom(*a, **k):
        raise RuntimeError("crash after inserting transactions")

    monkeypatch.setattr(database, "insert_import_issues", boom)
    with pytest.raises(RuntimeError):
        pipeline.commit_import(conn, preview)
    assert database.count_transactions(conn) == 0
    assert conn.execute("SELECT COUNT(*) FROM statements").fetchone()[0] == 0


def test_bulk_edit_only_touches_that_merchant(client):
    tx = client.get("/api/transactions?merchants=Zomato&page_size=250", headers=DEMO).json()
    before = client.get("/api/transactions?merchants=Swiggy&page_size=250", headers=DEMO).json()["rows"]
    r = client.patch(f"/api/transactions/{tx['rows'][0]['id']}", headers=DEMO,
                     json={"category": "Travel", "apply_to_merchant": True, "expected_count": tx["total"]})
    assert r.json()["updated"] == tx["total"]
    assert client.get("/api/transactions?merchants=Swiggy&page_size=250", headers=DEMO).json()["rows"] == before


@pytest.mark.parametrize("body,status", [
    ({"category": "Not a category"}, 400), ({"transaction_type": "salary"}, 400),
    ({"category": "Travel", "apply_to_merchant": True}, 409),
    ({"category": "Travel", "apply_to_merchant": True, "expected_count": 0}, 422),
    ({"transaction_type": "expense", "apply_to_merchant": True}, 400),
])
def test_invalid_corrections(client, body, status):
    assert client.patch("/api/transactions/1", json=body, headers=DEMO).status_code == status


def test_malformed_requests(client):
    assert client.patch("/api/transactions/1", content=b"{bad", headers={**DEMO, "Content-Type": "application/json"}).status_code == 422
    assert client.put("/api/transactions/1", json={}, headers=DEMO).status_code == 405
    assert client.patch("/api/transactions/abc", json={}, headers=DEMO).status_code == 422
    assert client.delete("/api/transactions/999999", headers=DEMO).status_code == 404
    assert client.post("/api/import/preview", headers=USER).status_code == 422
    assert client.get("/api/transactions?page=0", headers=DEMO).status_code == 422
    assert client.get("/api/transactions?page_size=10000", headers=DEMO).status_code == 422


def test_concurrent_reads_and_writes(client):
    errors = []

    def reader():
        for _ in range(5):
            r = client.get("/api/overview", headers=DEMO)
            if r.status_code != 200:
                errors.append(r.status_code)

    def writer():
        for m in ("2026-10", "2026-11", "2026-12"):
            r = client.post("/api/budgets", json={"month": m, "category": "Travel", "amount": "100"}, headers=DEMO)
            if r.status_code not in {201, 409}:
                errors.append(r.status_code)

    threads = [threading.Thread(target=reader) for _ in range(6)] + [threading.Thread(target=writer) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    with main.connections.connection("demo", None) as conn:
        assert conn.execute("SELECT COUNT(*) FROM budgets WHERE category='Travel'").fetchone()[0] == 3


def test_demo_and_user_never_mix(client):
    tok = upload(client, bank_statement_pdf(bank_rows(3))).json()["token"]
    client.post(f"/api/import/{tok}/commit", json={}, headers=USER)
    assert client.get("/api/meta", headers=DEMO).json()["counts"]["transactions"] == 284
    client.post("/api/demo/reset", headers=DEMO)
    assert client.get("/api/meta", headers=USER).json()["counts"]["transactions"] == 3
    client.request("DELETE", "/api/data", json={"confirm": "DELETE"}, headers=USER)
    assert client.get("/api/meta", headers=DEMO).json()["counts"]["transactions"] == 284
    # A demo preview token can't be committed in user mode, and vice versa.
    assert client.post("/api/import/preview", headers=DEMO,
                       files={"file": ("s.pdf", bank_statement_pdf(bank_rows(2)), "application/pdf")}).status_code == 409


def test_import_logs_contain_no_statement_content(client, caplog):
    rows = bank_rows(3, desc="UPI/DR/4{i:05d}/RAHUL KUMAR/YESB/rahul.k@okhdfc/Payment")
    caplog.set_level(logging.DEBUG)
    tok = upload(client, bank_statement_pdf(rows)).json()["token"]
    client.post(f"/api/import/{tok}/commit", json={}, headers=USER)
    text = caplog.text
    assert "RAHUL" not in text and "okhdfc" not in text and "XXXXXXXX4521" not in text
    stored = client.get("/api/transactions", headers=USER).json()["rows"]
    assert all("@" not in r["description"] for r in stored)


def test_uploads_are_not_written_to_disk(client, tmp_path):
    before = {p for p in tmp_path.rglob("*") if p.is_file()}
    tok = upload(client, bank_statement_pdf(bank_rows(2))).json()["token"]
    client.post(f"/api/import/{tok}/commit", json={}, headers=USER)
    new = {p for p in tmp_path.rglob("*") if p.is_file()} - before
    assert all(p.suffix in {".db", ".db-journal", ".db-wal", ".db-shm"} for p in new)
    assert not list(tmp_path.rglob("*.pdf"))
