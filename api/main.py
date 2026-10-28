"""Spendly API.

Run locally:   uvicorn api.main:app --reload --port 8000

Every endpoint reuses the existing modules — ``src.analytics`` (SQL files),
``src.insights``, ``src.subscription_detector``, ``src.anomaly_detector``,
``src.pipeline`` and ``src.database`` — so the API and the Streamlit app share a
single definition of every metric.

Request headers
    X-Spendly-Mode     "demo" (default) or "user" — which database to use
    X-Spendly-Session  random id; required only when SPENDLY_PUBLIC_DEPLOYMENT=true
"""

from __future__ import annotations

import io
import os
from datetime import date
from typing import Annotated, Literal

import pandas as pd
from fastapi import Body, Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from api.serialize import clean, records, transaction_rows
from api.state import MODES, ConnectionManager, PreviewStore, SessionError, is_public
from src import ai, analytics, anomaly_detector, config, database, insights, pipeline, subscription_detector
from src.analytics import FilterError, Filters
from src.categorizer import type_for_manual_category
from src.pdf_parser import PasswordRequiredError, StatementError, supported_formats
from src.privacy import get_logger

log = get_logger("spendly.api")

app = FastAPI(title="Spendly API", version="2.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")

_origins = [o.strip() for o in os.getenv("SPENDLY_CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-Spendly-Mode", "X-Spendly-Session"],
)

connections = ConnectionManager(public=is_public())
previews = PreviewStore()


# ---------------------------------------------------------------- errors

@app.exception_handler(FilterError)
async def _filter_error(_: Request, exc: FilterError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(SessionError)
async def _session_error(_: Request, exc: SessionError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def _unexpected(_: Request, exc: Exception):
    # Never echo internals or payloads; log the type only.
    log.error("Unhandled API error: %s", type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong. Please try again."})


# ----------------------------------------------------------- dependencies

class Ctx:
    def __init__(self, mode: str, session: str | None):
        self.mode = mode
        self.session = session

    def conn(self):
        return connections.connection(self.mode, self.session)

    @property
    def owner(self) -> str:
        return connections.owner(self.session)


def ctx(
    x_spendly_mode: Annotated[str, Header()] = "demo",
    x_spendly_session: Annotated[str | None, Header()] = None,
) -> Ctx:
    if x_spendly_mode not in MODES:
        raise HTTPException(400, "X-Spendly-Mode must be 'demo' or 'user'.")
    connections.owner(x_spendly_session)  # validates the session on public deployments
    return Ctx(x_spendly_mode, x_spendly_session)


CtxDep = Annotated[Ctx, Depends(ctx)]


def filters_dep(
    start: date | None = None,
    end: date | None = None,
    categories: Annotated[list[str], Query()] = [],  # noqa: B006 - FastAPI query lists
    types: Annotated[list[str], Query()] = [],  # noqa: B006
    merchants: Annotated[list[str], Query()] = [],  # noqa: B006
    statuses: Annotated[list[str], Query()] = [],  # noqa: B006
    search: Annotated[str, Query(max_length=100)] = "",
) -> Filters:
    bad_categories = set(categories) - set(config.CATEGORIES)
    if bad_categories:
        raise HTTPException(400, f"Unknown category: {sorted(bad_categories)[0]}")
    bad_types = set(types) - set(config.TRANSACTION_TYPES)
    if bad_types:
        raise HTTPException(400, f"Unknown transaction type: {sorted(bad_types)[0]}")
    if len(merchants) > 50:
        raise HTTPException(400, "Too many merchants in one filter.")
    return Filters(start_date=start, end_date=end, categories=tuple(categories), transaction_types=tuple(types),
                   merchants=tuple(merchants), statuses=tuple(statuses), search=search)


FiltersDep = Annotated[Filters, Depends(filters_dep)]


# ------------------------------------------------------------------ helpers

def _comparison(comp) -> dict | None:
    if comp is None:
        return None
    return {
        "current": {"start": comp.current[0].isoformat(), "end": comp.current[1].isoformat(),
                    "label": comp.current_label},
        "previous": {"start": comp.previous[0].isoformat(), "end": comp.previous[1].isoformat(),
                     "label": comp.previous_label},
        "is_partial": comp.is_partial,
        "current_paise": comp.current_paise,
        "previous_paise": comp.previous_paise,
        "change_paise": comp.change_paise,
        "change_pct": comp.change_pct,
    }


def _insight(i: insights.Insight) -> dict:
    return clean({
        "key": i.key, "title": i.title, "text": i.text, "tone": i.tone, "period": i.period,
        "value_paise": i.value_paise, "value_pct": i.value_pct, "subject": i.subject, "link": i.link,
    })


def _coverage(conn) -> dict:
    start, end = database.coverage_period(conn)
    return {"start": start, "end": end}


def _quality_counts(conn) -> dict:
    statements = database.list_statements(conn)
    totals = analytics.totals(conn)
    return {
        "rows_extracted": sum(s["rows_extracted"] for s in statements),
        "rows_invalid": sum(s["rows_invalid"] for s in statements),
        "duplicates_skipped": sum(s["rows_skipped_duplicates"] for s in statements),
        "balance_checked_pairs": sum(s["balance_checked_pairs"] for s in statements),
        "balance_mismatches": sum(s["balance_mismatches"] for s in statements),
        "possible_duplicates": int(totals["possible_duplicate_count"] or 0),
        "uncategorized": int(totals["uncategorized_count"] or 0),
        "needs_review": int(totals["needs_review_count"] or 0),
    }


def _recurring(conn, filters: Filters):
    _, data_end = analytics.date_bounds(conn)
    return subscription_detector.detect_recurring(
        analytics.recurring_candidates(conn, filters, config.RECURRING.min_occurrences),
        database.recurring_decisions(conn), as_of=filters.end_date or data_end)


# ------------------------------------------------------------------ meta

@app.get("/api/health")
def health():
    return {"ok": True, "public": is_public()}


@app.get("/api/meta")
def meta(c: CtxDep):
    with c.conn() as conn:
        lo, hi = analytics.date_bounds(conn)
        enabled, message = ai.ai_status()
        return clean({
            "mode": c.mode,
            "public": is_public(),
            "date_bounds": {"min": lo, "max": hi},
            "coverage": _coverage(conn),
            "categories": config.CATEGORIES,
            "transaction_types": [{"key": k, "label": v} for k, v in config.TRANSACTION_TYPES.items()],
            "merchants": analytics.distinct_values(conn, "normalized_merchant"),
            "counts": {"transactions": database.count_transactions(conn),
                       "statements": len(database.list_statements(conn))},
            "ai": {"enabled": enabled, "message": message},
            "upload": {"max_mb": config.UPLOAD.max_file_size_mb, "max_pages": config.UPLOAD.max_pages,
                       "formats": supported_formats()},
            "storage": "memory" if is_public() else ("file" if c.mode == "user" else "demo-file"),
        })


# --------------------------------------------------------------- overview

@app.get("/api/overview")
def overview(c: CtxDep, f: FiltersDep):
    with c.conn() as conn:
        totals = analytics.totals(conn, f)
        monthly = analytics.monthly_summary(conn, f)
        comp = insights.compare_periods(conn, f)
        anomalies, _ = anomaly_detector.detect_anomalies(analytics.transactions(conn, f),
                                                         database.anomaly_reviews(conn))
        items = insights.build_insights(conn, f, _recurring(conn, f), anomalies)
        recent = analytics.transactions(conn, f, limit=8)
        return {
            "totals": clean(totals),
            "monthly": records(monthly.drop(columns=["month"], errors="ignore")),
            "categories": records(analytics.category_spending(conn, f)),
            "top_merchants": records(analytics.top_merchants(conn, f, limit=5)),
            "recent": transaction_rows(recent),
            "comparison": _comparison(comp),
            "insights": [_insight(i) for i in items],
            "quality": _quality_counts(conn),
            "coverage": _coverage(conn),
        }


# ------------------------------------------------------------ transactions

SortKey = Literal["date", "merchant", "category", "type", "amount"]


@app.get("/api/transactions")
def list_transactions(
    c: CtxDep, f: FiltersDep,
    sort: SortKey = "date",
    order: Literal["asc", "desc"] = "desc",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=250)] = 50,
):
    with c.conn() as conn:
        total = analytics.count_transactions(conn, f)
        rows = analytics.transactions(conn, f, sort=sort, descending=order == "desc",
                                      limit=page_size, offset=(page - 1) * page_size)
        clause, params = analytics.build_filter_clause(f)
        summary = conn.execute(
            "SELECT COALESCE(SUM(CASE WHEN direction='debit' THEN amount_paise END),0),"
            " COALESCE(SUM(CASE WHEN direction='credit' THEN amount_paise END),0),"
            " SUM(CASE WHEN review_status='needs_review' THEN 1 ELSE 0 END)"
            " FROM transactions WHERE 1 = 1" + clause, params).fetchone()
        return {
            "rows": transaction_rows(rows),
            "total": total,
            "page": page,
            "page_size": page_size,
            "summary": {"debits_paise": summary[0], "credits_paise": summary[1], "needs_review": summary[2] or 0},
        }


@app.get("/api/transactions/export.csv")
def export_csv(c: CtxDep, f: FiltersDep):
    with c.conn() as conn:
        frame = analytics.transactions(conn, f)
    export = pd.DataFrame({
        "transaction_date": frame["transaction_date"],
        "merchant": frame["normalized_merchant"],
        "description": frame["description"],
        "direction": frame["direction"],
        "amount_inr": (frame["amount_paise"] / 100).round(2),
        "transaction_type": frame["transaction_type"],
        "category": frame["category"],
        "categorization_method": frame["categorization_method"],
        "review_status": frame["review_status"],
        "balance_inr": (frame["balance_paise"] / 100).round(2),
    }) if not frame.empty else pd.DataFrame(columns=["transaction_date", "merchant", "description", "direction",
                                                     "amount_inr", "transaction_type", "category",
                                                     "categorization_method", "review_status", "balance_inr"])
    buffer = io.StringIO()
    export.to_csv(buffer, index=False)
    return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="spendly_transactions.csv"'})


@app.get("/api/transactions/{transaction_id}/merchant-scope")
def merchant_scope(transaction_id: int, c: CtxDep):
    with c.conn() as conn:
        row = database.get_transaction(conn, transaction_id)
        if row is None:
            raise HTTPException(404, "Transaction not found.")
        count = conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE normalized_merchant = ? AND direction = ?",
            (row["normalized_merchant"], row["direction"])).fetchone()[0]
        return {"merchant": row["normalized_merchant"], "direction": row["direction"], "count": count}


class TransactionPatch(BaseModel):
    category: str | None = None
    transaction_type: str | None = None
    mark_reviewed: bool = False
    apply_to_merchant: bool = False
    # Required with apply_to_merchant: the row count the user confirmed, so a
    # bulk change never touches more rows than they agreed to.
    expected_count: int | None = Field(default=None, ge=1)


@app.patch("/api/transactions/{transaction_id}")
def update_transaction(transaction_id: int, body: TransactionPatch, c: CtxDep):
    if body.category is not None and body.category not in config.CATEGORIES:
        raise HTTPException(400, "Unknown category.")
    if body.transaction_type is not None and body.transaction_type not in config.TRANSACTION_TYPES:
        raise HTTPException(400, "Unknown transaction type.")
    if body.apply_to_merchant and body.category is None:
        raise HTTPException(400, "Merchant-wide changes only apply to the category.")
    with c.conn() as conn:
        record = database.get_transaction(conn, transaction_id)
        if record is None:
            raise HTTPException(404, "Transaction not found.")

        def changes_for(row: dict, explicit_type: str | None) -> dict:
            changes: dict = {}
            new_type = explicit_type or row["transaction_type"]
            if body.category is not None and body.category != row["category"]:
                changes["category"] = body.category
                if explicit_type is None:
                    new_type = type_for_manual_category(body.category, row["direction"], row["transaction_type"])
            if new_type != row["transaction_type"]:
                changes["transaction_type"] = new_type
            return changes

        targets = [record]
        if body.apply_to_merchant:
            ids = [r[0] for r in conn.execute(
                "SELECT id FROM transactions WHERE normalized_merchant = ? AND direction = ? ORDER BY id",
                (record["normalized_merchant"], record["direction"]))]
            if body.expected_count != len(ids):
                raise HTTPException(409, f"This would change {len(ids)} transactions; please confirm again.")
            targets = [database.get_transaction(conn, i) for i in ids]

        updated = 0
        for row in targets:
            changes = changes_for(row, body.transaction_type if row["id"] == transaction_id else None)
            if row["id"] == transaction_id and body.mark_reviewed:
                changes["review_status"] = "reviewed"
                changes["is_possible_duplicate"] = 0
            if changes:
                database.update_transaction_fields(conn, row["id"], changes)
                updated += 1
        return {"updated": updated}


@app.delete("/api/transactions/{transaction_id}")
def remove_transaction(transaction_id: int, c: CtxDep):
    with c.conn() as conn:
        if database.get_transaction(conn, transaction_id) is None:
            raise HTTPException(404, "Transaction not found.")
        database.delete_transaction(conn, transaction_id)
        return {"deleted": 1}


# --------------------------------------------------------------- insights

@app.get("/api/insights")
def insights_page(c: CtxDep, f: FiltersDep):
    with c.conn() as conn:
        comp = insights.compare_periods(conn, f)
        txns = analytics.transactions(conn, f)
        flagged, info = anomaly_detector.detect_anomalies(txns, database.anomaly_reviews(conn), include_reviewed=True)
        items = insights.build_insights(conn, f, _recurring(conn, f),
                                        flagged[flagged["review_status"] == "new"] if not flagged.empty else flagged)
        result = {
            "comparison": _comparison(comp),
            "headline": _insight(insights.describe_change(comp)) if comp else None,
            "category_changes": records(comp.categories) if comp else [],
            "merchant_changes": records(comp.merchants[comp.merchants["change_paise"] != 0]) if comp else [],
            "insights": [_insight(i) for i in items],
            "weekday": records(analytics.weekday_spending(conn, f)),
            "largest": records(analytics.largest_transactions(conn, f, limit=8)),
            "anomalies": records(flagged),
            "anomaly_info": clean(info),
        }
        return result


class AnomalyReview(BaseModel):
    status: Literal["dismissed", "expected"]


@app.post("/api/anomalies/{transaction_id}")
def review_anomaly(transaction_id: int, body: AnomalyReview, c: CtxDep):
    with c.conn() as conn:
        if database.get_transaction(conn, transaction_id) is None:
            raise HTTPException(404, "Transaction not found.")
        database.set_anomaly_review(conn, transaction_id, body.status)
        return {"ok": True}


# -------------------------------------------------------------- recurring

@app.get("/api/recurring")
def recurring(c: CtxDep, f: FiltersDep):
    with c.conn() as conn:
        candidates = _recurring(conn, f)
        monthly = subscription_detector.recurring_monthly_total(candidates)
        return {
            "candidates": [clean(cand) for cand in candidates],
            "monthly_total_paise": monthly,
            "annual_total_paise": monthly * 12,
            "settings": {
                "min_occurrences": config.RECURRING.min_occurrences,
                "tolerance_days": config.RECURRING.interval_tolerance_days,
                "high_amount_tolerance": config.RECURRING.high_confidence_amount_tolerance,
                "possible_amount_tolerance": config.RECURRING.possible_amount_tolerance,
            },
        }


class RecurringDecision(BaseModel):
    merchant: str = Field(min_length=1, max_length=120)
    decision: Literal["confirmed", "rejected"] | None


@app.post("/api/recurring/decision")
def recurring_decision(body: RecurringDecision, c: CtxDep):
    with c.conn() as conn:
        database.set_recurring_decision(conn, body.merchant, body.decision)
        return {"ok": True}


# ----------------------------------------------------------- data quality

@app.get("/api/quality")
def quality(c: CtxDep):
    with c.conn() as conn:
        statements = database.list_statements(conn)
        issues = pd.read_sql_query(
            """SELECT s.display_name AS statement, i.page, i.row_number, i.reason
               FROM import_issues i JOIN statements s ON s.id = i.statement_id
               ORDER BY i.statement_id, i.row_number""", conn)
        breakdown: dict[str, int] = {}
        for reason in issues["reason"] if not issues.empty else []:
            for part in reason.split("; "):
                kind = "Ambiguous date" if "ambiguous" in part else part.split(":", 1)[0]
                breakdown[kind] = breakdown.get(kind, 0) + 1
        missing = conn.execute(
            "SELECT SUM(balance_paise IS NULL), SUM(normalized_merchant = 'Unknown'), COUNT(*) FROM transactions"
        ).fetchone()
        corrections = pd.read_sql_query(
            """SELECT m.corrected_at, t.normalized_merchant AS merchant, m.field, m.old_value, m.new_value
               FROM manual_corrections m JOIN transactions t ON t.id = m.transaction_id
               ORDER BY m.id DESC LIMIT 20""", conn)
        return {
            "counts": {**_quality_counts(conn),
                       "rows_without_balance": int(missing[0] or 0),
                       "rows_unknown_merchant": int(missing[1] or 0),
                       "transactions": int(missing[2] or 0),
                       "manual_corrections": int(conn.execute("SELECT COUNT(*) FROM manual_corrections").fetchone()[0])},
            "statements": clean(statements),
            "issues": records(issues),
            "issue_breakdown": [{"kind": k, "count": v} for k, v in sorted(breakdown.items())],
            "uncategorized": records(analytics.uncategorized(conn)),
            "corrections": records(corrections),
        }


# ----------------------------------------------------------------- import

def _preview_payload(token: str, preview: pipeline.ImportPreview) -> dict:
    q = preview.quality
    enabled, message = ai.ai_status()
    uncategorized = sorted({r["normalized_merchant"] for r in preview.rows
                            if r["categorization_method"] == "none" and r["direction"] == "debit"})
    rows = [{
        "row_number": r["row_number"], "page": r["page"], "date": r["transaction_date"],
        "description": r["description"], "merchant": r["normalized_merchant"],
        "amount_paise": r["amount_paise"], "direction": r["direction"], "type": r["transaction_type"],
        "category": r["category"], "method": r["categorization_method"],
        "duplicate_status": r["duplicate_status"], "review_reason": r["review_reason"],
    } for r in preview.rows]
    return clean({
        "token": token,
        "parser": {"name": preview.parser_name, "label": preview.parser_label},
        "period": {"start": preview.period_start, "end": preview.period_end},
        "counts": {
            "extracted": q.total_extracted, "valid": q.valid, "invalid": q.invalid,
            "exact_duplicates": preview.exact_duplicates, "possible_duplicates": preview.possible_duplicates,
            "uncategorized": preview.uncategorized,
            "to_import": len(preview.rows) - preview.exact_duplicates,
        },
        "balance_check": {"checked_pairs": q.balance_check.checked_pairs, "mismatches": q.balance_check.mismatches},
        "warnings": preview.warnings,
        "already_imported": preview.already_imported,
        "rows": rows,
        "invalid_rows": preview.invalid_rows,
        "ai": {"enabled": enabled, "message": message,
               "payload": ai.preview_payload(uncategorized) if enabled else [],
               "uncategorized_merchants": len(uncategorized)},
    })


def _require_user_mode(c: Ctx) -> None:
    if c.mode != "user":
        raise HTTPException(409, "Switch to “My data” to import statements — demo data is read-only sample data.")


@app.post("/api/import/preview")
async def import_preview(
    c: CtxDep,
    file: Annotated[UploadFile, File()],
    password: Annotated[str | None, Form()] = None,
):
    _require_user_mode(c)
    limit = config.UPLOAD.max_file_size_bytes
    data = await file.read(limit + 1)  # read in memory only; never written to disk
    if len(data) > limit:
        raise HTTPException(413, f"The file is larger than {config.UPLOAD.max_file_size_mb} MB.")
    try:
        with c.conn() as conn:
            preview = pipeline.prepare_pdf_import(data, file.filename or "statement.pdf", conn, password or None)
    except PasswordRequiredError as exc:
        raise HTTPException(401, str(exc)) from exc
    except StatementError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        del data
    token = previews.put(c.owner, c.mode, preview)
    return _preview_payload(token, preview)


@app.get("/api/import/{token}")
def import_get(token: str, c: CtxDep):
    preview = previews.get(token, c.owner, c.mode)
    if preview is None:
        raise HTTPException(404, "This preview has expired. Please upload the statement again.")
    return _preview_payload(token, preview)


@app.post("/api/import/{token}/ai")
def import_ai(token: str, c: CtxDep):
    preview = previews.get(token, c.owner, c.mode)
    if preview is None:
        raise HTTPException(404, "This preview has expired. Please upload the statement again.")
    merchants = sorted({r["normalized_merchant"] for r in preview.rows
                        if r["categorization_method"] == "none" and r["direction"] == "debit"})
    try:
        changed = pipeline.apply_ai_suggestions(preview, ai.suggest_categories(merchants))
    except ai.AIError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"changed": changed, "preview": _preview_payload(token, preview)}


class CommitBody(BaseModel):
    include_exact_duplicates: bool = False


@app.post("/api/import/{token}/commit")
def import_commit(token: str, c: CtxDep, body: CommitBody = Body(default_factory=CommitBody)):
    _require_user_mode(c)
    preview = previews.get(token, c.owner, c.mode)
    if preview is None:
        raise HTTPException(404, "This preview has expired. Please upload the statement again.")
    if preview.already_imported:
        raise HTTPException(409, "This exact file has already been imported.")
    with c.conn() as conn:
        statement_id = pipeline.commit_import(conn, preview, include_exact_duplicates=body.include_exact_duplicates)
        statement = next(s for s in database.list_statements(conn) if s["id"] == statement_id)
    previews.pop(token, c.owner, c.mode)
    flagged = sum(1 for r in preview.rows if r["review_status"] == "needs_review"
                  and (body.include_exact_duplicates or not r["duplicate_status"].startswith("exact")))
    return {
        "statement_id": statement_id,
        "imported": statement["rows_imported"],
        "skipped_duplicates": statement["rows_skipped_duplicates"],
        "invalid": statement["rows_invalid"],
        "flagged_for_review": flagged,
    }


@app.delete("/api/import/{token}")
def import_discard(token: str, c: CtxDep):
    previews.pop(token, c.owner, c.mode)
    return {"ok": True}


# ---------------------------------------------------------------- settings

@app.post("/api/demo/reset")
def demo_reset(c: CtxDep):
    if c.mode != "demo":
        raise HTTPException(409, "Only the demo data can be reset.")
    with c.conn() as conn:
        pipeline.load_demo_dataset(conn)
        return {"transactions": database.count_transactions(conn)}


class DeleteBody(BaseModel):
    confirm: str


@app.delete("/api/data")
def delete_all(body: DeleteBody, c: CtxDep):
    if c.mode != "user":
        raise HTTPException(409, "Switch to “My data” to delete your imported data.")
    if body.confirm != "DELETE":
        raise HTTPException(400, 'Type "DELETE" to confirm.')
    with c.conn() as conn:
        database.clear_all_data(conn)
    previews.discard_owner(c.owner)
    return {"ok": True}


@app.post("/api/ai/summary")
def ai_summary(c: CtxDep, f: FiltersDep):
    enabled, message = ai.ai_status()
    if not enabled:
        raise HTTPException(409, message)
    with c.conn() as conn:
        items = insights.build_insights(conn, f, _recurring(conn, f))
    try:
        summary = ai.rephrase_insights([i.text for i in items])
    except ai.AIError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"summary": summary, "validated": summary is not None}
