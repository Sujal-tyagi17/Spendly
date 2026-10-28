"""API tests: the HTTP layer must return exactly what the analytics modules compute."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from api import main
from api.state import ConnectionManager, PreviewStore
from src import analytics, config, database, pipeline
from src.sample_pdfs import bank_statement_pdf, image_only_pdf

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


def _bank_pdf(rows=5):
    out, balance = [], 50_000_00
    for i in range(rows):
        amount = 250_00 + i * 100
        balance -= amount
        out.append({"date": date(2026, 7, 1 + i), "description": f"UPI/DR/41234567890{i}/ZOMATO/YESB",
                    "debit": amount, "credit": None, "balance": balance})
    return bank_statement_pdf(out)


def test_health_and_meta(client):
    assert client.get("/api/health").json()["ok"] is True
    meta = client.get("/api/meta", headers=DEMO).json()
    assert meta["mode"] == "demo" and meta["counts"]["transactions"] == 284
    assert meta["date_bounds"] == {"min": "2026-04-01", "max": "2026-09-30"}
    assert "Food & Dining" in meta["categories"]
    assert meta["upload"]["max_mb"] == config.UPLOAD.max_file_size_mb


def test_invalid_mode_rejected(client):
    assert client.get("/api/meta", headers={"X-Spendly-Mode": "admin"}).status_code == 400


def test_overview_matches_sql_layer(client, demo_conn):
    data = client.get("/api/overview", headers=DEMO).json()
    expected = analytics.totals(demo_conn)
    for key in ("expenditure_paise", "income_paise", "refunds_paise", "net_cash_flow_paise", "transfers_paise"):
        assert data["totals"][key] == expected[key]
    assert len(data["monthly"]) == 6
    assert data["comparison"]["change_pct"] == -60.8
    assert data["categories"][0]["category"] == "Rent & Housing"
    keys = {i["key"] for i in data["insights"]}
    assert {"overall_change", "largest_category", "top_merchant"} <= keys


def test_filters_are_applied(client):
    r = client.get("/api/overview", params={"start": "2026-08-01", "end": "2026-08-31",
                                             "categories": ["Shopping"]}, headers=DEMO).json()
    assert r["totals"]["expenditure_paise"] > 5_000_000
    assert {c["category"] for c in r["categories"]} == {"Shopping"}
    assert client.get("/api/overview", params={"categories": ["Gambling"]}, headers=DEMO).status_code == 400
    assert client.get("/api/overview", params={"start": "2026-09-01", "end": "2026-01-01"},
                      headers=DEMO).status_code == 400


def test_transactions_paging_sorting_and_search(client):
    page = client.get("/api/transactions", params={"page_size": 10, "sort": "amount", "order": "asc"},
                      headers=DEMO).json()
    assert page["total"] == 284 and len(page["rows"]) == 10
    assert page["rows"][0]["amount_paise"] == 54_999_00 and page["rows"][0]["direction"] == "debit"
    found = client.get("/api/transactions", params={"search": "netflix"}, headers=DEMO).json()
    assert found["total"] == 6 and {r["merchant"] for r in found["rows"]} == {"Netflix"}
    dups = client.get("/api/transactions", params={"statuses": ["possible_duplicate"]}, headers=DEMO).json()
    assert dups["total"] == 1 and dups["rows"][0]["is_possible_duplicate"] is True
    assert client.get("/api/transactions", params={"sort": "id; DROP"}, headers=DEMO).status_code == 422
    assert client.get("/api/transactions", params={"statuses": ["evil"]}, headers=DEMO).status_code == 400


def test_edit_single_and_merchant_wide_with_confirmation(client):
    rows = client.get("/api/transactions", params={"search": "Sharma General"}, headers=DEMO).json()["rows"]
    target = rows[0]["id"]
    scope = client.get(f"/api/transactions/{target}/merchant-scope", headers=DEMO).json()
    assert scope["count"] == 8

    # Wrong confirmation count -> refused, nothing changes.
    r = client.patch(f"/api/transactions/{target}", json={"category": "Groceries", "apply_to_merchant": True,
                                                          "expected_count": 3}, headers=DEMO)
    assert r.status_code == 409
    assert client.get("/api/transactions", params={"search": "Sharma General", "categories": ["Groceries"]},
                      headers=DEMO).json()["total"] == 0

    r = client.patch(f"/api/transactions/{target}", json={"category": "Groceries", "apply_to_merchant": True,
                                                          "expected_count": 8}, headers=DEMO)
    assert r.json() == {"updated": 8}
    after = client.get("/api/transactions", params={"search": "Sharma General"}, headers=DEMO).json()["rows"]
    assert {(r["category"], r["method"], r["review_status"]) for r in after} == {("Groceries", "manual", "reviewed")}

    # Unrelated merchants untouched
    salon = client.get("/api/transactions", params={"search": "Green Leaf"}, headers=DEMO).json()["rows"]
    assert {r["category"] for r in salon} == {"Other"}


def test_edit_validation(client):
    assert client.patch("/api/transactions/1", json={"category": "Gambling"}, headers=DEMO).status_code == 400
    assert client.patch("/api/transactions/99999", json={"category": "Other"}, headers=DEMO).status_code == 404
    assert client.patch("/api/transactions/1", json={"amount_paise": 1}, headers=DEMO).json() == {"updated": 0}


def test_mark_reviewed_clears_duplicate_flag(client):
    dup = client.get("/api/transactions", params={"statuses": ["possible_duplicate"]}, headers=DEMO).json()["rows"][0]
    client.patch(f"/api/transactions/{dup['id']}", json={"mark_reviewed": True}, headers=DEMO)
    assert client.get("/api/transactions", params={"statuses": ["possible_duplicate"]}, headers=DEMO).json()["total"] == 0


def test_csv_export_respects_filters(client):
    r = client.get("/api/transactions/export.csv", params={"merchants": ["Netflix"]}, headers=DEMO)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    assert lines[0].startswith("transaction_date,merchant") and len(lines) == 7
    assert all(",Netflix," in line for line in lines[1:])


def test_insights_recurring_quality(client):
    ins = client.get("/api/insights", headers=DEMO).json()
    assert ins["comparison"]["current"]["label"] == "September 2026"
    assert ins["anomalies"][0]["amount_paise"] == 54_999_00
    linked = [i for i in ins["insights"] if i["link"]]
    assert linked and all(i["period"] for i in ins["insights"])

    rec = client.get("/api/recurring", headers=DEMO).json()
    names = {c["merchant"] for c in rec["candidates"] if c["status"] == "high_confidence"}
    assert {"Netflix", "Spotify"} <= names
    assert rec["annual_total_paise"] == rec["monthly_total_paise"] * 12

    client.post("/api/recurring/decision", json={"merchant": "Netflix", "decision": "rejected"}, headers=DEMO)
    rec = client.get("/api/recurring", headers=DEMO).json()
    assert next(c for c in rec["candidates"] if c["merchant"] == "Netflix")["status"] == "rejected"

    q = client.get("/api/quality", headers=DEMO).json()
    assert q["counts"]["duplicates_skipped"] == 1 and q["counts"]["balance_mismatches"] == 0
    assert q["counts"]["possible_duplicates"] == 1


def test_anomaly_review(client):
    ins = client.get("/api/insights", headers=DEMO).json()
    first = ins["anomalies"][0]["id"]
    assert client.post(f"/api/anomalies/{first}", json={"status": "dismissed"}, headers=DEMO).status_code == 200
    again = client.get("/api/insights", headers=DEMO).json()
    assert next(a for a in again["anomalies"] if a["id"] == first)["review_status"] == "dismissed"
    assert client.post(f"/api/anomalies/{first}", json={"status": "fraud"}, headers=DEMO).status_code == 422


def test_import_flow_preview_then_commit(client):
    pdf = _bank_pdf()
    # Nothing is saved by the preview step.
    r = client.post("/api/import/preview", headers=USER, files={"file": ("s.pdf", pdf, "application/pdf")})
    assert r.status_code == 200, r.text
    preview = r.json()
    assert preview["counts"]["to_import"] == 5 and preview["parser"]["name"] == "bank_table"
    assert client.get("/api/meta", headers=USER).json()["counts"]["transactions"] == 0
    assert "412345678900" not in r.text  # identifiers already masked

    done = client.post(f"/api/import/{preview['token']}/commit", json={}, headers=USER).json()
    assert done["imported"] == 5
    assert client.get("/api/meta", headers=USER).json()["counts"]["transactions"] == 5
    # Token is single-use; same file is blocked on re-upload.
    assert client.post(f"/api/import/{preview['token']}/commit", json={}, headers=USER).status_code == 404
    again = client.post("/api/import/preview", headers=USER,
                        files={"file": ("s.pdf", pdf, "application/pdf")}).json()
    assert again["already_imported"] is True
    # A different file containing the same rows is caught by duplicate detection instead.
    overlap = client.post("/api/import/preview", headers=USER,
                          files={"file": ("s2.pdf", _bank_pdf(), "application/pdf")}).json()
    assert overlap["already_imported"] is False and overlap["counts"]["exact_duplicates"] == 5
    assert client.post(f"/api/import/{again['token']}/commit", json={}, headers=USER).status_code == 409


def test_demo_and_user_data_are_isolated(client):
    assert client.post("/api/import/preview", headers=DEMO,
                       files={"file": ("s.pdf", _bank_pdf(), "application/pdf")}).status_code == 409
    user = client.get("/api/meta", headers=USER).json()
    assert user["counts"]["transactions"] == 0
    assert client.get("/api/overview", headers=USER).json()["totals"]["transaction_count"] == 0
    assert client.get("/api/meta", headers=DEMO).json()["counts"]["transactions"] == 284


def test_import_errors_are_friendly(client):
    r = client.post("/api/import/preview", headers=USER, files={"file": ("scan.pdf", image_only_pdf(), "application/pdf")})
    assert r.status_code == 422 and "OCR" in r.json()["detail"]
    r = client.post("/api/import/preview", headers=USER, files={"file": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 422
    big = b"%PDF-1.4" + b"0" * (config.UPLOAD.max_file_size_bytes + 1)
    assert client.post("/api/import/preview", headers=USER,
                       files={"file": ("big.pdf", big, "application/pdf")}).status_code == 413


def test_delete_requires_confirmation_and_user_mode(client):
    token = client.post("/api/import/preview", headers=USER,
                        files={"file": ("s.pdf", _bank_pdf(), "application/pdf")}).json()["token"]
    client.post(f"/api/import/{token}/commit", json={}, headers=USER)
    assert client.request("DELETE", "/api/data", json={"confirm": "yes"}, headers=USER).status_code == 400
    assert client.request("DELETE", "/api/data", json={"confirm": "DELETE"}, headers=DEMO).status_code == 409
    assert client.request("DELETE", "/api/data", json={"confirm": "DELETE"}, headers=USER).json() == {"ok": True}
    assert client.get("/api/meta", headers=USER).json()["counts"]["transactions"] == 0


def test_preview_does_not_write_pdf_to_disk(client, tmp_path):
    client.post("/api/import/preview", headers=USER, files={"file": ("s.pdf", _bank_pdf(), "application/pdf")})
    assert not list(tmp_path.rglob("*.pdf"))


def test_public_mode_isolates_sessions(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "connections", ConnectionManager(public=True))
    monkeypatch.setattr(main, "previews", PreviewStore())
    with TestClient(main.app) as c:
        a = {**USER, "X-Spendly-Session": "a" * 24}
        b = {**USER, "X-Spendly-Session": "b" * 24}
        assert c.get("/api/meta", headers=USER).status_code == 400  # session required
        token = c.post("/api/import/preview", headers=a,
                       files={"file": ("s.pdf", _bank_pdf(), "application/pdf")}).json()["token"]
        assert c.post(f"/api/import/{token}/commit", json={}, headers=b).status_code == 404  # not B's preview
        c.post(f"/api/import/{token}/commit", json={}, headers=a)
        assert c.get("/api/meta", headers=a).json()["counts"]["transactions"] == 5
        assert c.get("/api/meta", headers=b).json()["counts"]["transactions"] == 0
        # Demo edits by one visitor don't leak to another.
        da = {**DEMO, "X-Spendly-Session": "a" * 24}
        db = {**DEMO, "X-Spendly-Session": "b" * 24}
        c.post("/api/recurring/decision", json={"merchant": "Netflix", "decision": "rejected"}, headers=da)
        rec_b = c.get("/api/recurring", headers=db).json()
        assert next(x for x in rec_b["candidates"] if x["merchant"] == "Netflix")["status"] == "high_confidence"
    assert not list(tmp_path.glob("*.db"))  # nothing written to disk in public mode
    main.connections.close_all()


def test_ai_summary_disabled_by_default(client, monkeypatch):
    monkeypatch.delenv("SPENDLY_ENABLE_AI", raising=False)
    assert client.post("/api/ai/summary", headers=DEMO).status_code == 409


def test_analysis_endpoint_matches_sql_layer(client, demo_conn):
    data = client.get("/api/analysis", headers=DEMO).json()
    assert data["totals"]["expenditure_paise"] == analytics.totals(demo_conn)["expenditure_paise"]
    assert data["concentration"]["top_merchant"] == "House Rent"
    assert data["merchants"][0]["merchant"] == "House Rent" and len(data["merchants"]) <= 25
    assert data["weekend"][0]["scope"] == "All categories"
    assert data["monthly"][-1]["cumulative_net_cash_flow_paise"] == data["totals"]["net_cash_flow_paise"]
    assert data["recurring"]["share_of_expenditure_pct"] is not None
    assert "is_expense" in data["definitions"]
    aug = client.get("/api/analysis", params={"start": "2026-08-01", "end": "2026-08-31"}, headers=DEMO).json()
    assert aug["range"] == {"start": "2026-08-01", "end": "2026-08-31"}
    assert {m["month_start"] for m in aug["monthly"]} == {"2026-08-01"}
