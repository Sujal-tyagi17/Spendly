"""Security regression tests: sessions, cross-session authorisation, rate limits, request
size, upload spooling, local-mode exposure, logging, headers, CORS, file permissions and
the single-process assumption. All data is synthetic."""

import io
import logging
import os
import socket
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import pytest
import starlette.formparsers as formparsers
from fastapi.testclient import TestClient

from api import main, security, state
from api.state import ConnectionManager, PreviewStore
from src import analytics, config
from src.sample_pdfs import bank_statement_pdf

USER = {"X-Spendly-Mode": "user"}
DEMO = {"X-Spendly-Mode": "demo"}
UNIQUE_MERCHANT = "ZYZZYVA QUOKKA CAFE"


def statement(n=4, merchant="ZOMATO", start_day=1):
    rows, bal = [], 1_00_000_00
    for i in range(n):
        bal -= (i + 1) * 100_00
        rows.append({"date": date(2026, 7, start_day + i), "description": f"UPI/DR/5{start_day}{i:04d}/{merchant}/YESB",
                     "debit": (i + 1) * 100_00, "credit": None, "balance": bal})
    return bank_statement_pdf(rows)


@pytest.fixture
def public(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setenv("SPENDLY_PUBLIC_DEPLOYMENT", "true")
    monkeypatch.setattr(main, "connections", ConnectionManager(public=True))
    monkeypatch.setattr(main, "previews", PreviewStore())
    with TestClient(main.app, raise_server_exceptions=False) as c:
        yield c
    main.connections.close_all()


@pytest.fixture
def local(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setenv("SPENDLY_PUBLIC_DEPLOYMENT", "false")
    monkeypatch.delenv("SPENDLY_ALLOW_REMOTE", raising=False)
    monkeypatch.setattr(main, "connections", ConnectionManager(public=False))
    monkeypatch.setattr(main, "previews", PreviewStore())
    with TestClient(main.app, raise_server_exceptions=False) as c:
        yield c
    main.connections.close_all()


def new_session(c) -> str:
    r = c.post("/api/session")
    assert r.status_code == 200
    return r.json()["session"]


def import_into(c, headers, pdf):
    tok = c.post("/api/import/preview", headers=headers, files={"file": ("s.pdf", pdf, "application/pdf")}).json()["token"]
    assert c.post(f"/api/import/{tok}/commit", json={}, headers=headers).status_code == 200


# ------------------------------------------------------------------ sessions

def test_sessions_are_server_issued_and_unpredictable(public):
    tokens = {new_session(public) for _ in range(5)}
    assert len(tokens) == 5 and all(len(t) == 43 for t in tokens)          # 32 random bytes, url-safe base64
    body = public.post("/api/session").json()
    assert body["public"] is True and body["ttl_seconds"] == state.SESSION_TTL_SECONDS


def test_local_mode_issues_no_session(local):
    assert local.post("/api/session").json() == {"session": None, "public": False, "ttl_seconds": None}
    assert local.delete("/api/session").status_code == 409


@pytest.mark.parametrize("token", [None, "", "short", "A" * 43, "../../etc/passwd", "x" * 65])
def test_missing_forged_or_malformed_sessions_are_rejected(public, token):
    headers = {**USER, **({"X-Spendly-Session": token} if token is not None else {})}
    r = public.get("/api/meta", headers=headers)
    assert r.status_code == 401 and r.json()["code"] == "session_required"
    assert token is None or not token or token not in r.text


def test_expired_session_is_rejected(public, monkeypatch):
    s = new_session(public)
    h = {**USER, "X-Spendly-Session": s}
    assert public.get("/api/meta", headers=h).status_code == 200
    later = time.time() + state.SESSION_TTL_SECONDS + 5
    monkeypatch.setattr(state.time, "time", lambda: later)
    assert public.get("/api/meta", headers=h).status_code == 401


def test_ended_session_is_revoked_and_its_data_erased(public):
    s = new_session(public)
    h = {**USER, "X-Spendly-Session": s}
    import_into(public, h, statement())
    assert public.delete("/api/session", headers=h).json() == {"ok": True}
    assert public.get("/api/meta", headers=h).status_code == 401
    assert public.delete("/api/session", headers=h).status_code == 401
    assert main.connections.session_count() == 0


def test_capacity_never_evicts_active_sessions(public, monkeypatch):
    monkeypatch.setattr(state, "MAX_SESSIONS", 2)
    a, b = new_session(public), new_session(public)
    r = public.post("/api/session")
    assert r.status_code == 503 and "Retry-After" in r.headers
    for s in (a, b):
        assert public.get("/api/meta", headers={**DEMO, "X-Spendly-Session": s}).status_code == 200
    # Once a session has been idle long enough it may make room for a new visitor.
    main.connections._issued[a] -= state.EVICTABLE_IDLE_SECONDS + 1
    assert public.post("/api/session").status_code == 200
    assert public.get("/api/meta", headers={**DEMO, "X-Spendly-Session": a}).status_code == 401
    assert public.get("/api/meta", headers={**DEMO, "X-Spendly-Session": b}).status_code == 200


def test_one_visitor_cannot_crowd_out_other_previews(public):
    a, b = new_session(public), new_session(public)
    hb = {**USER, "X-Spendly-Session": b}
    tok_b = public.post("/api/import/preview", headers=hb, files={"file": ("s.pdf", statement(), "application/pdf")}).json()["token"]
    ha = {**USER, "X-Spendly-Session": a}
    tokens_a = [public.post("/api/import/preview", headers=ha, files={"file": ("s.pdf", statement(start_day=d), "application/pdf")})
                .json()["token"] for d in (1, 5, 9, 13, 17)]
    assert public.get(f"/api/import/{tok_b}", headers=hb).status_code == 200              # B's preview survives
    alive = [t for t in tokens_a if public.get(f"/api/import/{t}", headers=ha).status_code == 200]
    assert alive == tokens_a[-state.MAX_PREVIEWS_PER_OWNER:]


# ------------------------------------------------- cross-session authorisation

def test_cross_session_isolation_matrix(public):
    sa, sb = new_session(public), new_session(public)
    A, B = {**USER, "X-Spendly-Session": sa}, {**USER, "X-Spendly-Session": sb}
    import_into(public, A, statement(4, "ZOMATO"))
    import_into(public, B, statement(3, "SWIGGY", start_day=10))
    a_rows = public.get("/api/transactions", headers=A).json()["rows"]
    b_rows = public.get("/api/transactions", headers=B).json()["rows"]
    assert {r["merchant"] for r in a_rows} == {"Zomato"} and {r["merchant"] for r in b_rows} == {"Swiggy"}
    a_id = a_rows[0]["id"]
    # Ids are per-database, so A's id either doesn't exist for B or points at B's own row — never at A's.
    public.patch(f"/api/transactions/{a_id}", json={"category": "Travel"}, headers=B)
    public.patch(f"/api/transactions/{a_id}", headers=B,
                 json={"category": "Travel", "apply_to_merchant": True, "expected_count": 3})
    public.delete(f"/api/transactions/{a_id}", headers=B)
    after = public.get("/api/transactions", headers=A).json()["rows"]
    assert after == a_rows                                                                  # A untouched
    # Read paths: B never sees A's merchant anywhere.
    for path in ["/api/overview", "/api/insights", "/api/analysis", "/api/recurring", "/api/quality", "/api/budgets",
                 "/api/transactions/export.csv", "/api/report/monthly?month=2026-07", "/api/meta"]:
        text = public.get(path, headers=B).text
        assert "Zomato" not in text and "ZOMATO" not in text, path
    assert "Zomato" in public.get("/api/transactions/export.csv", headers=A).text
    # Pending imports can't be read, committed or discarded by another session.
    tok = public.post("/api/import/preview", headers=A, files={"file": ("s.pdf", statement(2, "UBER INDIA", 20), "application/pdf")}).json()["token"]
    assert public.get(f"/api/import/{tok}", headers=B).status_code == 404
    assert public.post(f"/api/import/{tok}/commit", json={}, headers=B).status_code == 404
    assert public.delete(f"/api/import/{tok}", headers=B).status_code == 404
    assert public.get(f"/api/import/{tok}", headers=A).status_code == 200
    # Deleting B's data and resetting B's demo leave A alone; demo stays separate from both.
    public.request("DELETE", "/api/data", json={"confirm": "DELETE"}, headers=B)
    public.post("/api/demo/reset", headers={**DEMO, "X-Spendly-Session": sb})
    assert public.get("/api/meta", headers=A).json()["counts"]["transactions"] == 4
    assert public.get("/api/meta", headers={**DEMO, "X-Spendly-Session": sa}).json()["counts"]["transactions"] == 284


# --------------------------------------------------------------- rate limits

def test_rate_limiter_window():
    now = [0.0]
    limiter = security.RateLimiter({"x": security.Limit(3, 60)}, clock=lambda: now[0])
    assert [limiter.check("x", "k") for _ in range(3)] == [None, None, None]
    assert limiter.check("x", "k") == pytest.approx(60)
    assert limiter.check("x", "other") is None                 # separate keys
    now[0] = 61
    assert limiter.check("x", "k") is None                     # window slid


def test_rate_limits_per_session_with_retry_after(public):
    a, b = new_session(public), new_session(public)
    ha = {**DEMO, "X-Spendly-Session": a}
    codes = [public.get("/api/report/monthly.pdf?month=2026-09", headers=ha).status_code for _ in range(21)]
    assert codes[:20] == [200] * 20 and codes[20] == 429
    r = public.get("/api/report/monthly.pdf?month=2026-09", headers=ha)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1 and "Too many requests" in r.json()["detail"]
    assert public.get("/api/report/monthly.pdf?month=2026-09", headers={**DEMO, "X-Spendly-Session": b}).status_code == 200


def test_session_creation_is_rate_limited(public):
    codes = [public.post("/api/session").status_code for _ in range(12)]
    assert codes[:10] == [200] * 10 and codes[10:] == [429, 429]


def test_global_session_cap_survives_ip_spoofing(public, monkeypatch):
    monkeypatch.setenv("SPENDLY_TRUST_PROXY", "true")
    monkeypatch.setattr(main.limiter, "limits", {**main.limiter.limits, "session_global": security.Limit(5, 60)})
    codes = [public.post("/api/session", headers={"X-Forwarded-For": f"203.0.113.{i}"}).status_code for i in range(7)]
    assert codes == [200] * 5 + [429, 429]


def test_rate_limits_off_in_local_mode_by_default(local):
    assert all(local.get("/api/report/monthly.pdf?month=2026-09", headers=DEMO).status_code == 200 for _ in range(22))


# ------------------------------------------------------ request size / uploads

def test_oversized_upload_rejected_before_the_body_is_read(local, monkeypatch):
    rolled = []

    class Spy(formparsers.SpooledTemporaryFile):
        def rollover(self):
            rolled.append(True)
            return super().rollover()

    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", Spy)
    huge = b"%PDF-1.4\n" + b"x" * (12 * 1024 * 1024)
    r = local.post("/api/import/preview", headers=USER, files={"file": ("s.pdf", huge, "application/pdf")})
    assert r.status_code == 413 and not rolled


def test_large_valid_upload_stays_in_memory(local, monkeypatch):
    """Regression: Starlette spooled uploads over 1 MB to a temporary file on disk."""
    rolled = []

    class Spy(formparsers.SpooledTemporaryFile):
        def rollover(self):
            rolled.append(True)
            return super().rollover()

    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", Spy)
    two_mb = b"%PDF-1.4\n" + b"%" + b"x" * (2 * 1024 * 1024)
    r = local.post("/api/import/preview", headers=USER, files={"file": ("s.pdf", two_mb, "application/pdf")})
    assert r.status_code == 422 and not rolled          # rejected as malformed, and never written to disk


def test_json_body_limit_and_length_checks(local):
    big = '{"category": "' + "x" * (70 * 1024) + '"}'
    assert local.patch("/api/transactions/1", content=big, headers={**DEMO, "Content-Type": "application/json"}).status_code == 413
    r = local.patch("/api/transactions/1", content=b'{"category": "Travel"}',
                    headers={**DEMO, "Content-Type": "application/json", "Content-Length": "abc"})
    assert r.status_code in {400, 422}


# --------------------------------------------------------- local-mode exposure

@pytest.mark.parametrize("peer", ["203.0.113.7", "10.0.0.5"])
def test_local_mode_refuses_remote_peers(tmp_path, monkeypatch, peer):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setenv("SPENDLY_PUBLIC_DEPLOYMENT", "false")
    monkeypatch.delenv("SPENDLY_ALLOW_REMOTE", raising=False)
    monkeypatch.setattr(main, "connections", ConnectionManager(public=False))
    with TestClient(main.app, client=(peer, 1234)) as c:
        r = c.get("/api/meta", headers=USER)
        assert r.status_code == 403 and "single-user local mode" in r.json()["detail"]
        monkeypatch.setenv("SPENDLY_ALLOW_REMOTE", "true")
        assert c.get("/api/meta", headers=USER).status_code == 200
    main.connections.close_all()


def test_local_mode_refuses_requests_relayed_for_a_public_host(local):
    assert local.get("/api/meta", headers={**USER, "X-Forwarded-Host": "spendly.example.com"}).status_code == 403
    assert local.get("/api/meta", headers={**USER, "X-Forwarded-Host": "localhost:3000"}).status_code == 200
    assert local.get("/api/meta", headers={**USER, "X-Forwarded-Host": "[::1]:3000"}).status_code == 200


def test_public_mode_accepts_remote_peers(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setenv("SPENDLY_PUBLIC_DEPLOYMENT", "true")
    monkeypatch.setattr(main, "connections", ConnectionManager(public=True))
    with TestClient(main.app, client=("203.0.113.7", 1234)) as c:
        s = c.post("/api/session").json()["session"]
        assert c.get("/api/meta", headers={**DEMO, "X-Spendly-Session": s}).status_code == 200
    main.connections.close_all()


# ------------------------------------------------------------------- logging

def test_access_log_filter_strips_query_strings():
    record = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
                               ("127.0.0.1:5", "GET", f"/api/overview?merchants={UNIQUE_MERCHANT}", "1.1", 200), None)
    security.AccessLogQueryFilter().filter(record)
    assert UNIQUE_MERCHANT not in record.getMessage() and "/api/overview?[redacted]" in record.getMessage()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_real_uvicorn_logs_contain_no_filters_or_session_tokens(tmp_path):
    """Starts the API exactly as documented and checks what it writes to its log."""
    port = _free_port()
    env = {**os.environ, "SPENDLY_DATA_DIR": str(tmp_path), "SPENDLY_PUBLIC_DEPLOYMENT": "true"}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "api.main:app", "--port", str(port)], env=env,
                            cwd=Path(__file__).resolve().parent.parent, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        import httpx
        base = f"http://127.0.0.1:{port}"
        for _ in range(60):
            try:
                if httpx.get(base + "/api/health").status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.25)
        token = httpx.post(base + "/api/session").json()["session"]
        h = {**DEMO, "X-Spendly-Session": token}
        httpx.get(base + "/api/overview", params={"merchants": UNIQUE_MERCHANT, "search": UNIQUE_MERCHANT}, headers=h)
        httpx.get(base + "/api/transactions", params={"statuses": UNIQUE_MERCHANT}, headers=h)           # 400 path
        httpx.get(base + "/api/transactions/export.csv", params={"merchants": UNIQUE_MERCHANT}, headers=h)
        httpx.get(base + "/api/meta", headers={**DEMO, "X-Spendly-Session": "F" * 43})                  # 401 path
        httpx.post(base + "/api/import/preview", headers={**USER, "X-Spendly-Session": token},
                   files={"file": ("s.pdf", statement(3, UNIQUE_MERCHANT.replace(" ", "")), "application/pdf")})
    finally:
        proc.terminate()
        out = proc.communicate(timeout=20)[0].decode(errors="ignore")
    assert "GET /api/overview?[redacted]" in out                       # requests are still logged
    assert UNIQUE_MERCHANT not in out and UNIQUE_MERCHANT.replace(" ", "") not in out
    assert token not in out and "F" * 43 not in out


def test_unhandled_error_hides_details_from_response_and_log(local, monkeypatch, caplog):
    def boom(*a, **k):
        raise RuntimeError(f"secret detail {UNIQUE_MERCHANT} /home/user/data")

    monkeypatch.setattr(analytics, "totals", boom)
    caplog.set_level(logging.DEBUG)
    r = local.get("/api/overview", headers=DEMO)
    assert r.status_code == 500 and r.json() == {"detail": "Something went wrong. Please try again."}
    assert UNIQUE_MERCHANT not in caplog.text and "/home/user" not in caplog.text
    assert "RuntimeError" in caplog.text


# ------------------------------------------------------------ headers / CORS

def test_api_security_headers(local):
    r = local.get("/api/overview", headers=DEMO)
    assert r.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert r.headers["cache-control"] == "no-store" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer" and r.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" not in local.get("/api/docs").headers   # Swagger UI needs its own scripts


def test_cors_allows_only_configured_origins(local):
    pre = {"Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "X-Spendly-Mode"}
    bad = local.options("/api/overview", headers={"Origin": "https://evil.example", **pre})
    assert bad.status_code == 400 and "access-control-allow-origin" not in bad.headers
    good = local.options("/api/overview", headers={"Origin": "http://localhost:3000", **pre})
    assert good.status_code == 200 and good.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-credentials" not in good.headers
    simple = local.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in simple.headers


# --------------------------------------------------------------- storage

@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")
def test_database_files_are_private(local, tmp_path):
    local.get("/api/meta", headers=USER)
    local.get("/api/meta", headers=DEMO)
    for name in ("spendly_user.db", "spendly_demo.db"):
        assert oct((tmp_path / name).stat().st_mode & 0o777) == "0o600", name


def test_public_mode_writes_nothing_to_disk(public, tmp_path):
    s = new_session(public)
    import_into(public, {**USER, "X-Spendly-Session": s}, statement())
    assert [p for p in tmp_path.rglob("*") if p.is_file()] == []


# -------------------------------------------------------- single-process model

def test_state_is_process_local():
    """Documents why public mode needs exactly one worker: a second process (or a restart)
    knows nothing about sessions or pending imports created by the first."""
    w1, w2 = ConnectionManager(public=True), ConnectionManager(public=True)
    token = w1.issue()
    with w1.connection("demo", token):
        pass
    with pytest.raises(state.SessionError):
        w2.owner(token)
    p1, p2 = PreviewStore(), PreviewStore()
    from src import pipeline
    preview = pipeline.prepare_pdf_import(statement(), "s.pdf", conn=None)
    tok = p1.put(token, "user", preview)
    assert p1.get(tok, token, "user") is not None and p2.get(tok, token, "user") is None
    w1.close_all()
    w2.close_all()


def test_multipart_spool_threshold_covers_the_upload_limit():
    assert formparsers.MultiPartParser.spool_max_size >= config.UPLOAD.max_file_size_bytes
    assert io  # keep import for clarity of the Spy subclasses above
