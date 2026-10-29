"""Timing of the main operations on synthetic accounts of increasing size.

    python -m scripts.benchmark            # 100, 1,000 and 10,000 transactions

Uses an in-memory database and FastAPI's TestClient (no network, no browser), so
the numbers are the server-side cost only. Results depend on the machine; they are
measurements, not guarantees.
"""

from __future__ import annotations

import platform
import random
import time
from datetime import date, timedelta

from fastapi.testclient import TestClient

from api import main
from api.state import ConnectionManager, PreviewStore
from src import pipeline
from src.sample_pdfs import bank_statement_pdf

MERCHANTS = ["UPI/DR/{r}/ZOMATO/YESB", "UPI/DR/{r}/BLINKIT/YESB", "POS/XXXX1111/AMZN MKTPLACE", "UPI/DR/{r}/UBER INDIA/YESB",
             "ACH/DR/{r}/NETFLIX.COM", "UPI/DR/{r}/SWIGGY/YESB", "UPI/DR/{r}/SHARMA STORES/YESB"]


def rows(n: int, seed: int = 1):
    rng, bal, day, out = random.Random(seed), 50_00_000_00, date(2024, 1, 1), []
    for i in range(n):
        day += timedelta(days=1) if rng.random() < 0.3 else timedelta(0)
        if i % 40 == 0:
            amt, desc, credit = 90_000_00, f"NEFT/CR/{i}/ACME TECH/SALARY", True
        else:
            amt, desc, credit = rng.randint(20, 5000) * 100, rng.choice(MERCHANTS).format(r=600000000000 + i), False
        bal += amt if credit else -amt
        out.append({"date": day, "description": desc, "debit": None if credit else amt, "credit": amt if credit else None,
                    "balance": bal})
    return out


def timed(fn):
    t = time.perf_counter()
    result = fn()
    return result, round((time.perf_counter() - t) * 1000)


def run(n: int) -> dict:
    data = rows(n)
    out = {"transactions": n}
    if n <= 1000:  # bigger PDFs exceed the 60-page upload limit by design
        pdf = bank_statement_pdf(data)
        preview, out["pdf_preview_ms"] = timed(lambda: pipeline.prepare_pdf_import(pdf, "s.pdf", conn=None))
        assert len(preview.rows) == n
    csv_text = "date,description,debit,credit,balance\n" + "".join(
        f"{r['date']},{r['description']},{(r['debit'] or 0) / 100 or ''},{(r['credit'] or 0) / 100 or ''},{r['balance'] / 100}\n"
        for r in data)
    main.connections = ConnectionManager(public=True)
    main.previews = PreviewStore()
    c = TestClient(main.app)
    main.limiter.reset()
    h = {"X-Spendly-Mode": "user", "X-Spendly-Session": main.connections.issue()}
    with main.connections.connection("user", h["X-Spendly-Session"]) as conn:
        p, out["csv_preview_ms"] = timed(lambda: pipeline.prepare_csv_rows_import(csv_text, display_name="b", conn=conn))
        _, out["commit_ms"] = timed(lambda: pipeline.commit_import(conn, p))
    for name, path in [("overview", "/api/overview"), ("transactions_page", "/api/transactions?page_size=50"),
                       ("filtered_overview", "/api/overview?categories=Food%20%26%20Dining&start=2024-03-01"),
                       ("insights", "/api/insights"), ("analysis", "/api/analysis"), ("recurring", "/api/recurring"),
                       ("quality", "/api/quality"), ("export_csv", "/api/transactions/export.csv"),
                       ("report_pdf", "/api/report/monthly.pdf")]:
        r, ms = timed(lambda: c.get(path, headers=h))
        assert r.status_code == 200, (path, r.status_code)
        out[f"{name}_ms"] = ms
    main.connections.close_all()
    return out


if __name__ == "__main__":
    print(f"Python {platform.python_version()} · {platform.machine()} · {platform.system()}")
    results = [run(n) for n in (100, 1_000, 10_000)]
    keys = [k for k in results[-1] if k != "transactions"] + (["pdf_preview_ms"] if "pdf_preview_ms" not in results[-1] else [])
    print("| operation | " + " | ".join(f"{r['transactions']:,} txns" for r in results) + " |")
    print("|---|" + "---|" * len(results))
    for k in dict.fromkeys(["pdf_preview_ms"] + keys):
        print(f"| {k.replace('_ms', '')} (ms) | " + " | ".join(str(r.get(k, "n/a (page limit)")) for r in results) + " |")
