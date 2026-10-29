"""Browser end-to-end journeys for the Spendly web app (Playwright, synthetic data only).

Prerequisites (three terminals, from the repo root):
    SPENDLY_DATA_DIR=/tmp/spendly-e2e uvicorn api.main:app --port 8000   # throwaway data folder
    cd web && npm run build && npx next start -p 3000
    python -m e2e.run_e2e --base http://localhost:3000 --api-log api.log \
        [--streamlit http://localhost:8501 --streamlit-db /tmp/spendly-st/spendly_user.db]

The script never touches your real data folder: point SPENDLY_DATA_DIR at an empty
temporary directory. It deletes "My data" in that instance at the start and the end.
Each check prints PASS/FAIL; the exit code is the number of failures.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
from datetime import date
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from src.money import format_inr
from src.sample_pdfs import bank_statement_pdf

RESULTS: list[dict] = []
FIXTURES = Path("/tmp/spendly-e2e-fixtures")


def check(journey: str, name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append({"journey": journey, "check": name, "status": "PASS" if ok else "FAIL", "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {journey}: {name}" + (f" — {detail}" if detail and not ok else ""))
    return ok


def api(page: Page, path: str, mode: str = "demo", method: str = "GET", body: dict | None = None):
    return page.evaluate(
        """async ([path, mode, method, body]) => {
            const r = await fetch(path, {method, headers: {'X-Spendly-Mode': mode, 'Content-Type': 'application/json',
              ...(sessionStorage.getItem('spendly.session') ? {'X-Spendly-Session': sessionStorage.getItem('spendly.session')} : {})},
              body: body ? JSON.stringify(body) : undefined});
            const text = await r.text();
            try { return {status: r.status, json: JSON.parse(text)}; } catch { return {status: r.status, text}; }
        }""", [path, mode, method, body])


def make_fixtures() -> dict[str, Path]:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    rows, bal = [], 50_000_00
    spec = [("UPI/DR/700001/ZOMATO/YESB/zomato@ybl", 450_00, "debit"), ("ACH/DR/700002/NETFLIX.COM", 649_00, "debit"),
            ("NEFT/CR/700003/ACME TECH/SALARY OCT", 60_000_00, "credit"), ("UPI/DR/700004/BLINKIT/YESB", 1_250_50, "debit"),
            ("IMPS/DR/700005/SELF TRANSFER TO OWN A/C", 5_000_00, "debit"), ("UPI/CR/700006/AMAZON REFUND/UTIB", 300_00, "credit"),
            ("POS/XXXX4521/AMZN MKTPLACE", 2_999_00, "debit"), ("UPI/DR/700008/UBER INDIA/YESB", 180_00, "debit")]
    for i, (desc, amt, d) in enumerate(spec):
        bal += amt if d == "credit" else -amt
        rows.append({"date": date(2026, 10, 2 + 3 * i), "description": desc, "debit": amt if d == "debit" else None,
                     "credit": amt if d == "credit" else None, "balance": bal})
    files = {
        "good": bank_statement_pdf(rows, period=(date(2026, 10, 1), date(2026, 10, 31)),
                                   opening_balance=50_000_00, closing_balance=bal),
        # A later statement that overlaps the last 3 rows (same balances → exact duplicates) plus 2 new rows.
        "overlap": bank_statement_pdf(rows[5:] + [
            {"date": date(2026, 10, 28), "description": "UPI/DR/700009/ZOMATO/YESB", "debit": 300_00, "credit": None,
             "balance": bal - 300_00},
            {"date": date(2026, 10, 30), "description": "UPI/DR/700010/SWIGGY/YESB", "debit": 200_00, "credit": None,
             "balance": bal - 500_00}]),
        "corrupt": b"%PDF-1.4\n%this is not really a pdf\x00\x01\x02",
    }
    paths = {}
    for name, data in files.items():
        p = FIXTURES / f"{name}.pdf"
        p.write_bytes(data)
        paths[name] = p
    txt = FIXTURES / "notes.txt"
    txt.write_text("not a statement")
    paths["txt"] = txt
    from reportlab.lib import pdfencrypt
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, encrypt=pdfencrypt.StandardEncryption("secret123", canPrint=0))
    c.drawString(50, 750, "locked")
    c.save()
    (FIXTURES / "locked.pdf").write_bytes(buf.getvalue())
    paths["locked"] = FIXTURES / "locked.pdf"
    paths["expected"] = rows  # type: ignore[assignment]
    return paths


def mtext(page: Page) -> str:
    # Next.js keeps the previous route mounted but hidden, so use the visible <main>.
    return page.locator("main:visible").first.inner_text()


def console_guard(page: Page, sink: list):
    page.on("pageerror", lambda e: sink.append(f"pageerror: {e}"))
    page.on("console", lambda m: m.type == "error" and sink.append(f"console: {m.text}"))


def set_mode(page: Page, base: str, mode: str):
    page.goto(f"{base}/app")
    page.wait_for_timeout(1200)
    page.get_by_role("radio", name="Demo" if mode == "demo" else "My data").first.click()
    page.wait_for_timeout(1500)


def import_file(page: Page, base: str, path: Path, password: str | None = None) -> str:
    page.goto(f"{base}/app/import")
    page.wait_for_timeout(1500)
    page.set_input_files("input[type=file]", str(path))
    page.wait_for_timeout(400)
    if not page.get_by_role("button", name="Read statement").is_enabled():
        return mtext(page)   # rejected in the browser before upload
    if password:
        pw = page.locator("input[type=password]")
        if pw.count():
            pw.first.fill(password)
    page.get_by_role("button", name="Read statement").click()
    page.wait_for_timeout(3500)
    return mtext(page)


# ----------------------------------------------------------------- journeys

def journey_a(page: Page, base: str, errors: list):
    J = "A first-time user"
    page.goto(base + "/")
    page.get_by_role("link", name="Try the demo").first.click()
    page.wait_for_selector("text=Why spending changed", timeout=20000)
    check(J, "demo opens from landing page with a synthetic-data banner", page.locator("text=Demo mode.").count() == 1)
    ov = api(page, "/api/overview")["json"]
    shown = mtext(page)
    check(J, "expenditure KPI equals API", format_inr(ov["executive"]["expenditure_paise"]) in shown)
    check(J, "income KPI equals API", format_inr(ov["executive"]["income_paise"]) in shown)
    for path, title in [("/app/transactions", "Transactions"), ("/app/insights", "Spending Insights"),
                        ("/app/recurring", "Recurring Payments"), ("/app/budgets", "Budget Planner"),
                        ("/app/analysis", "SQL Analysis"), ("/app/quality", "Data Quality"), ("/app/import", "Import & Settings")]:
        page.goto(base + path)
        page.wait_for_timeout(2200)
        ok = page.locator("h1").first.inner_text() == title and page.locator("text=Something went wrong").count() == 0
        check(J, f"page {path} loads", ok)
    # filters: Latest month preset + Groceries category
    page.goto(base + "/app")
    page.wait_for_selector("text=Why spending changed")
    page.get_by_role("button", name="All dates").click()
    page.get_by_role("button", name="Latest month").click()
    page.wait_for_timeout(1500)
    page.get_by_role("button", name="Filters").click()
    page.locator("[aria-haspopup=listbox]").first.click()
    page.get_by_role("option", name="Groceries").click()
    page.keyboard.press("Escape")
    page.wait_for_timeout(2000)
    f_ov = api(page, "/api/overview?start=2026-09-01&end=2026-09-30&categories=Groceries")["json"]
    text = mtext(page)
    check(J, "date + category filter reflected in KPIs", format_inr(f_ov["executive"]["expenditure_paise"]) in text,
          f"expected {format_inr(f_ov['executive']['expenditure_paise'])}")
    # transactions under the same filters + open one
    page.goto(base + "/app/transactions")
    page.wait_for_timeout(2500)
    tx = api(page, "/api/transactions?start=2026-09-01&end=2026-09-30&categories=Groceries&page_size=250")["json"]
    rows = page.locator("tbody tr")
    check(J, "transactions list honours the filters", rows.count() == tx["total"], f"{rows.count()} vs {tx['total']}")
    page.locator("main:visible tbody tr").first.get_by_role("button").last.click()
    page.wait_for_timeout(800)
    dialog = page.get_by_role("dialog")
    check(J, "transaction opens in an edit dialog", dialog.count() >= 1)
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    check(J, "dialog closes with Escape", page.get_by_role("dialog").count() == 0)
    # CSV export equals API rows
    with page.expect_download() as dl:
        page.get_by_role("button", name="Export CSV").click()
    data = list(csv.DictReader(io.StringIO(Path(dl.value.path()).read_text())))
    check(J, "CSV export = filtered rows", len(data) == tx["total"] and
          round(sum(float(r["amount_inr"]) for r in data) * 100) == sum(r["amount_paise"] for r in tx["rows"]))
    # insight drill-down
    page.evaluate("sessionStorage.removeItem('spendly.filters.demo')")
    page.goto(base + "/app/insights")
    page.wait_for_timeout(2500)
    opener = page.get_by_role("button", name="See transactions")
    if opener.count() == 0:
        opener = page.locator("article button").filter(has_text="transactions")
    check(J, "insight has a drill-down", opener.count() > 0)
    page.goto(base + "/app/recurring")
    page.wait_for_timeout(2000)
    rec = api(page, "/api/recurring")["json"]
    check(J, "recurring page shows the API's monthly total", format_inr(rec["monthly_total_paise"]) in mtext(page))
    page.goto(base + "/app/quality")
    page.wait_for_timeout(2000)
    check(J, "data-quality findings shown", page.locator("text=Validation findings").count() == 1)
    # PDF report
    page.goto(base + "/app")
    page.wait_for_selector("text=Monthly report (PDF)")
    with page.expect_download() as dl:
        page.get_by_role("button", name="Monthly report (PDF)").click()
    import pdfplumber
    with pdfplumber.open(dl.value.path()) as pdf:
        ptext = "\n".join(p.extract_text() or "" for p in pdf.pages)
    sep = api(page, "/api/overview?start=2026-09-01&end=2026-09-30")["json"]["executive"]
    check(J, "PDF report matches dashboard for the month", format_inr(sep["expenditure_paise"]) in ptext and "SYNTHETIC DEMO DATA" in ptext)


def journey_b(page: Page, base: str, fx: dict):
    J = "B import a statement"
    set_mode(page, base, "user")
    text = import_file(page, base, fx["good"])
    page.locator("summary", has_text="Validation report").click()
    text = mtext(page)
    check(J, "preview shows 8 rows ready to import", "ready to import 8" in " ".join(text.lower().split()), text[:400])
    check(J, "validation report reconciles opening → closing", "reconciles" in text.lower(), text[-600:])
    check(J, "debits/credits shown with correct sign", "−₹450.00" in text.replace("-", "−") and "+₹60,000.00" in text)
    page.get_by_role("button", name="Import 8 transactions").click()
    page.wait_for_timeout(2500)
    ov = api(page, "/api/overview", "user")["json"]
    # Expected by hand: spending = 450 + 649 + 1,250.50 + 2,999 + 180 = 5,528.50 (transfer excluded); refund 300
    check(J, "expenditure = hand-computed ₹5,528.50", ov["executive"]["expenditure_paise"] == 5_528_50, str(ov["executive"]["expenditure_paise"]))
    check(J, "income = ₹60,000, refunds = ₹300", ov["executive"]["income_paise"] == 60_000_00 and ov["executive"]["refunds_paise"] == 300_00)
    page.goto(base + "/app")
    page.wait_for_timeout(2500)
    check(J, "overview shows imported expenditure", "₹5,529" in mtext(page) or "₹5,528" in mtext(page))
    q = api(page, "/api/quality", "user")["json"]
    rec = q["scorecard"]["dimensions"][-1]
    check(J, "data quality: statement reconciliation 1 of 1", (rec["numerator"], rec["denominator"]) == (1, 1))
    page.goto(base + "/app/transactions")
    page.wait_for_timeout(2500)
    with page.expect_download() as dl:
        page.get_by_role("button", name="Export CSV").click()
    data = list(csv.DictReader(io.StringIO(Path(dl.value.path()).read_text())))
    exp = fx["expected"]
    got = sorted((r["transaction_date"], round(float(r["amount_inr"]) * 100), r["direction"]) for r in data)
    want = sorted((e["date"].isoformat(), e["debit"] or e["credit"], "debit" if e["debit"] else "credit") for e in exp)
    check(J, "CSV export equals source rows (date, paise, direction)", got == want)
    check(J, "UPI IDs masked in export", not any("@" in r["description"] for r in data))


def journey_c(page: Page, base: str, fx: dict):
    J = "C invalid statements"
    before = api(page, "/api/meta", "user")["json"]["counts"]
    text = import_file(page, base, fx["txt"])
    check(J, "non-PDF rejected with a clear message", "Only PDF statements are supported" in text)
    text = import_file(page, base, fx["corrupt"])
    check(J, "corrupted PDF fails safely", "damaged or malformed" in text)
    text = import_file(page, base, fx["locked"], password="wrong-password")
    check(J, "wrong password explained", "didn't open" in text or "password" in text.lower())
    after = api(page, "/api/meta", "user")["json"]["counts"]
    check(J, "no partial records after failures", before == after, f"{before} → {after}")
    page.goto(base + "/app")
    page.wait_for_timeout(1500)
    check(J, "app still usable afterwards", page.locator("text=Why spending changed").count() == 1)


def journey_d(page: Page, base: str, fx: dict):
    J = "D duplicates"
    before = api(page, "/api/overview", "user")["json"]["executive"]
    text = import_file(page, base, fx["good"])
    check(J, "re-importing the same file is blocked", "already been imported" in text)
    text = import_file(page, base, fx["overlap"])
    check(J, "overlapping statement: 3 exact duplicates will be skipped", "exact duplicates 3" in " ".join(text.lower().split()), text[:400])
    page.get_by_role("button", name="Import 2 transactions").click()
    page.wait_for_timeout(2500)
    after = api(page, "/api/overview", "user")["json"]["executive"]
    check(J, "totals not doubled (only the 2 new rows added: ₹500)", after["expenditure_paise"] - before["expenditure_paise"] == 500_00,
          f"{before['expenditure_paise']} → {after['expenditure_paise']}")
    q = api(page, "/api/quality", "user")["json"]
    codes = {i["code"]: i["count"] for i in q["scorecard"]["issues"]}
    check(J, "data quality records the skipped duplicates", codes.get("exact_duplicate") == 3, str(codes))


def journey_e(page: Page, base: str):
    J = "E filters and exports"
    set_mode(page, base, "demo")
    full = api(page, "/api/overview")["json"]["executive"]["expenditure_paise"]
    combos = {
        "date": "start=2026-07-01&end=2026-07-31",
        "category": "categories=Food%20%26%20Dining",
        "merchant": "merchants=Zomato",
        "combined": "start=2026-06-01&end=2026-08-31&categories=Food%20%26%20Dining&merchants=Zomato",
    }
    for name, q in combos.items():
        ov = api(page, f"/api/overview?{q}")["json"]
        tx = api(page, f"/api/transactions?{q}&types=expense&page_size=250")["json"]
        csv_text = api(page, f"/api/transactions/export.csv?{q}&types=expense")["text"]
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        ok = (sum(r["amount_paise"] for r in tx["rows"]) == ov["executive"]["expenditure_paise"]
              and len(rows) == tx["total"] and ov["executive"]["expenditure_paise"] <= full)
        check(J, f"{name} filter: KPI = sum of listed expenses = export", ok)
    page.goto(base + "/app/transactions?status=")
    page.evaluate("sessionStorage.removeItem('spendly.filters.demo')")
    page.goto(base + "/app")
    page.wait_for_timeout(2500)
    check(J, "clearing filters restores the original total", format_inr(full) in mtext(page))


def journey_f(page: Page, base: str, api_log: Path | None):
    J = "F demo and privacy"
    user_before = api(page, "/api/meta", "user")["json"]["counts"]
    first = api(page, "/api/transactions?page_size=1")["json"]["rows"][0]
    api(page, f"/api/transactions/{first['id']}", "demo", "PATCH", {"category": "Travel"})
    api(page, "/api/demo/reset", "demo", "POST")
    restored = api(page, "/api/transactions?page_size=1")["json"]["rows"][0]
    check(J, "demo reset restores the original category", restored["category"] == first["category"])
    check(J, "demo actions don't touch My data", api(page, "/api/meta", "user")["json"]["counts"] == user_before)
    r = api(page, "/api/data", "demo", "DELETE", {"confirm": "DELETE"})
    check(J, "'delete all' refuses to run on demo data", r["status"] == 409)
    api(page, "/api/data", "user", "DELETE", {"confirm": "DELETE"})
    check(J, "deleting My data leaves the demo intact", api(page, "/api/meta")["json"]["counts"]["transactions"] == 284)
    check(J, "My data is empty after delete", api(page, "/api/meta", "user")["json"]["counts"] == {"transactions": 0, "statements": 0})
    if api_log and api_log.exists():
        log = api_log.read_text(errors="ignore")
        leaked = [s for s in ("zomato@ybl", "ACME TECH", "XXXXXXXX4521", "SALARY OCT") if s in log]
        check(J, "API log has no statement content", not leaked, str(leaked))


def responsive_and_a11y(browser, base: str):
    J = "Responsive / a11y"
    pages = ["/app", "/app/transactions", "/app/insights", "/app/recurring", "/app/budgets", "/app/analysis",
             "/app/quality", "/app/import"]
    for w, h in [(375, 812), (768, 1024), (1440, 900)]:
        ctx = browser.new_context(viewport={"width": w, "height": h})
        p = ctx.new_page()
        p.goto(base + "/app?mode=demo")
        p.wait_for_timeout(1500)
        bad = []
        for path in pages:
            p.goto(base + path)
            p.wait_for_timeout(1800)
            if p.evaluate("document.documentElement.scrollWidth - window.innerWidth") > 0:
                bad.append(path)
        check(J, f"no horizontal overflow at {w}×{h}", not bad, str(bad))
        if w == 375:
            p.goto(base + "/app/transactions")
            p.wait_for_timeout(2000)
            p.locator("main:visible li button").first.click()
            p.wait_for_timeout(700)
            box = p.get_by_role("dialog").first.bounding_box()
            check(J, "edit dialog fits a 375 px screen", bool(box) and box["x"] >= 0 and box["x"] + box["width"] <= w + 1)
            p.keyboard.press("Escape")
            menu = p.get_by_role("button", name="Open navigation")
            check(J, "mobile navigation button present", menu.count() > 0)
            if menu.count():
                menu.first.click()
                p.wait_for_timeout(600)
                p.get_by_role("link", name="Data Quality").last.click()
                p.wait_for_timeout(2000)
                check(J, "mobile navigation opens and navigates", p.url.endswith("/app/quality"))
        ctx.close()
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
    p = ctx.new_page()
    p.goto(base + "/app?mode=demo")
    p.wait_for_selector("text=Why spending changed", timeout=20000)
    # keyboard: tab through the first 25 focusable elements, each must show a focus indicator
    missing = []
    for _ in range(25):
        p.keyboard.press("Tab")
        info = p.evaluate("""() => { const e = document.activeElement; if (!e || e === document.body) return null;
            const s = getComputedStyle(e); return {tag: e.tagName, label: e.getAttribute('aria-label') || e.textContent.trim().slice(0, 30),
            visible: (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none'}; }""")
        if info and not info["visible"]:
            missing.append(info["label"])
    check(J, "keyboard focus is visible on the first 25 tab stops", not missing, str(missing[:5]))
    unlabeled = p.evaluate("""() => [...document.querySelectorAll('button, a[href], input, select, textarea')]
        .filter(e => e.offsetParent !== null || e.type === 'file')
        .filter(e => !(e.getAttribute('aria-label') || e.getAttribute('aria-labelledby') || e.textContent.trim()
            || e.labels?.length || e.getAttribute('title')))
        .map(e => e.outerHTML.slice(0, 80))""")
    check(J, "every control has an accessible name (overview)", not unlabeled, str(unlabeled[:3]))
    imgs = p.evaluate("() => [...document.images].filter(i => !i.hasAttribute('alt')).length")
    check(J, "images have alt text", imgs == 0)
    check(J, "single h1 on the page", p.locator("h1").count() == 1)
    tokens = p.evaluate("""() => { const s = getComputedStyle(document.documentElement);
        return Object.fromEntries(['fg','muted','faint','lime','pos','neg','warn','err','info','ink','card','elevated']
          .map(k => [k, s.getPropertyValue('--color-' + k).trim()])); }""")
    def lum(h):
        r, g, b = (int(h.lstrip('#')[i:i + 2], 16) / 255 for i in (0, 2, 4))
        f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
    def ratio(a, b):
        hi, lo = sorted([lum(a), lum(b)], reverse=True)
        return (hi + 0.05) / (lo + 0.05)
    low = [f"{t} on {bg}: {ratio(tokens[t], tokens[bg]):.2f}" for t in ("fg", "muted", "faint", "lime", "pos", "neg", "warn", "err", "info")
           for bg in ("ink", "card", "elevated") if ratio(tokens[t], tokens[bg]) < 4.5]
    check(J, "text colour tokens meet WCAG AA 4.5:1 on all surfaces", not low, str(low))
    ctx.close()
    # skip link after client-side navigation from the landing page
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    p = ctx.new_page()
    p.goto(base + "/")
    p.get_by_role("link", name="Try the demo").first.click()
    p.wait_for_selector("text=Why spending changed", timeout=20000)
    p.evaluate("document.querySelector('a[href=\"#main\"]').focus()")   # the landing page's <main> is still mounted, hidden
    p.keyboard.press("Enter")
    p.wait_for_timeout(300)
    check(J, "skip link focuses the visible main content", p.evaluate(
        "document.activeElement.tagName === 'MAIN' && document.activeElement.offsetParent !== null"))
    # dialogs: Escape closes the confirm dialog and focus returns
    p.goto(base + "/app/import")
    p.wait_for_timeout(1500)
    p.get_by_role("button", name="Reset demo data").click()
    p.wait_for_timeout(400)
    opened = p.get_by_role("dialog").count() == 1
    p.keyboard.press("Escape")
    p.wait_for_timeout(400)
    check(J, "confirm dialog opens and closes with Escape", opened and p.get_by_role("dialog").count() == 0)
    ctx.close()


def journey_g(page: Page, st_base: str, fx: dict, st_db: Path | None = None):
    J = "G Streamlit"
    for path in ["", "transactions", "insights", "recurring", "data_quality", "home"]:
        page.goto(f"{st_base}/{path}")
        page.wait_for_timeout(7000)
        ok = page.locator("[data-testid=stException]").count() == 0 and len(page.locator("[data-testid=stMain]").inner_text()) > 200
        check(J, f"page /{path} renders without exceptions", ok)
    page.goto(f"{st_base}/home")
    page.wait_for_timeout(6000)
    radio = page.get_by_text("My data", exact=True)
    if radio.count():
        radio.first.click()
        page.wait_for_timeout(4000)
    inp = page.locator("input[type=file]")
    if not inp.count():
        check(J, "statement upload in Streamlit", False, "no file input found")
        return
    inp.first.set_input_files(str(fx["good"]))
    page.wait_for_timeout(9000)
    text = " ".join(page.locator("[data-testid=stMain]").inner_text().split())
    check(J, "Streamlit preview: 8 rows found, 8 ready to import", "ROWS FOUND 8" in text and "READY TO IMPORT 8" in text,
          text[:300])
    page.get_by_role("button", name="Import transactions").click()
    page.wait_for_timeout(8000)
    if st_db and st_db.exists():
        import sqlite3
        con = sqlite3.connect(st_db)
        n, spend = con.execute("SELECT COUNT(*), SUM(CASE WHEN transaction_type='expense' THEN amount_paise END) "
                               "FROM transactions").fetchone()
        con.close()
        check(J, "Streamlit import stored 8 rows, expenditure ₹5,528.50", (n, spend) == (8, 5_528_50), f"{n}, {spend}")
    else:
        check(J, "Streamlit import stored rows", False, "pass --streamlit-db to verify (BLOCKED otherwise)")


def journey_public(browser, base: str, fx: dict):
    """Run against an API started with SPENDLY_PUBLIC_DEPLOYMENT=true."""
    J = "P public sessions"
    a_ctx, b_ctx = browser.new_context(), browser.new_context()
    a, b = a_ctx.new_page(), b_ctx.new_page()
    for p in (a, b):
        p.goto(base + "/app?mode=demo")
        p.wait_for_selector("text=Why spending changed", timeout=30000)
    sa = a.evaluate("sessionStorage.getItem('spendly.session')")
    sb = b.evaluate("sessionStorage.getItem('spendly.session')")
    check(J, "each browser gets its own server-issued session", bool(sa) and bool(sb) and sa != sb and len(sa) >= 40)
    set_mode(a, base, "user")
    text = import_file(a, base, fx["good"])
    a.get_by_role("button", name="Import 8 transactions").click()
    a.wait_for_timeout(2500)
    check(J, "A sees its import", api(a, "/api/meta", "user")["json"]["counts"]["transactions"] == 8)
    check(J, "B sees none of A's data", api(b, "/api/meta", "user")["json"]["counts"]["transactions"] == 0)
    tx = api(a, "/api/transactions?page_size=1", "user")["json"]["rows"][0]
    check(J, "B can't delete A's transaction by id", api(b, f"/api/transactions/{tx['id']}", "user", "DELETE")["status"] == 404
          and api(a, "/api/meta", "user")["json"]["counts"]["transactions"] == 8)
    forged = b.evaluate("""async () => (await fetch('/api/meta', {headers: {'X-Spendly-Mode': 'user',
        'X-Spendly-Session': 'A'.repeat(43)}})).status""")
    check(J, "a made-up session token is rejected (401)", forged == 401)
    api(a, "/api/session", "user", "DELETE")
    a.reload()
    a.wait_for_timeout(3000)
    new = a.evaluate("sessionStorage.getItem('spendly.session')")
    check(J, "after ending the session the app starts a fresh one, with A's data gone",
          new and new != sa and api(a, "/api/meta", "user")["json"]["counts"]["transactions"] == 0)
    statuses = a.evaluate("""async () => { const out = [];
        for (let i = 0; i < 24; i++) { const r = await fetch('/api/report/monthly.pdf?month=2026-09',
          {headers: {'X-Spendly-Mode': 'demo', 'X-Spendly-Session': sessionStorage.getItem('spendly.session')}});
          out.push(r.status); } return out; }""")
    check(J, "report generation is rate-limited (20 per minute, then 429)",
          statuses[:20] == [200] * 20 and statuses[20:] == [429] * 4, str(statuses))
    a_ctx.close()
    b_ctx.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:3000")
    ap.add_argument("--streamlit", default=None)
    ap.add_argument("--api-log", default=None)
    ap.add_argument("--streamlit-db", default=None, help="the Streamlit instance's spendly_user.db (throwaway)")
    ap.add_argument("--out", default="e2e/results.json")
    ap.add_argument("--public", action="store_true", help="the API runs with SPENDLY_PUBLIC_DEPLOYMENT=true: run only the session journey")
    args = ap.parse_args()
    fx = make_fixtures()
    errors: list[str] = []
    start = time.time()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
        page = ctx.new_page()
        console_guard(page, errors)
        if args.public:
            try:
                journey_public(browser, args.base, fx)
            except Exception as exc:
                check("P", "journey completed", False, f"{type(exc).__name__}: {str(exc)[:200]}")
            browser.close()
            failed = sum(r["status"] == "FAIL" for r in RESULTS)
            print(f"\n{len(RESULTS) - failed} passed, {failed} failed")
            return failed
        page.goto(args.base + "/app")
        page.wait_for_timeout(1500)
        api(page, "/api/data", "user", "DELETE", {"confirm": "DELETE"})   # start from an empty My data
        api(page, "/api/demo/reset", "demo", "POST")
        for name, fn in [("A", lambda: journey_a(page, args.base, errors)), ("B", lambda: journey_b(page, args.base, fx)),
                         ("C", lambda: journey_c(page, args.base, fx)), ("D", lambda: journey_d(page, args.base, fx)),
                         ("E", lambda: journey_e(page, args.base)),
                         ("F", lambda: journey_f(page, args.base, Path(args.api_log) if args.api_log else None)),
                         ("R", lambda: responsive_and_a11y(browser, args.base))]:
            try:
                fn()
            except Exception as exc:  # keep going: report the journey as failed
                check(name, "journey completed", False, f"{type(exc).__name__}: {str(exc)[:200]}")
        relevant = [e for e in errors if "Failed to load resource" not in e]
        check("All", "no unexpected browser console errors", not relevant, str(relevant[:3]))
        if args.streamlit:
            try:
                journey_g(ctx.new_page(), args.streamlit, fx, Path(args.streamlit_db) if args.streamlit_db else None)
            except Exception as exc:
                check("G", "journey completed", False, f"{type(exc).__name__}: {str(exc)[:200]}")
        api(page, "/api/demo/reset", "demo", "POST")
        browser.close()
    failed = sum(r["status"] == "FAIL" for r in RESULTS)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"seconds": round(time.time() - start), "results": RESULTS}, indent=1))
    print(f"\n{len(RESULTS) - failed} passed, {failed} failed")
    return failed


if __name__ == "__main__":
    sys.exit(main())
