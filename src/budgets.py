"""Budget planner: storage, budget-vs-actual metrics, insights and spending pace.

Budgets live in the ``budgets`` table of the same SQLite database as the
transactions, so demo data, your data and (on public hosting) each visitor's
session keep their own budgets automatically.

Definitions (also in the README):
    actual       Expenditure for the month — the canonical {{is_expense}} rule.
                 Refunds are reported separately, not netted per category.
    variance     actual − budget         positive = spent more than the budget
    remaining    budget − actual         negative = overspent
    utilisation  actual / budget × 100   undefined (None) when the budget is 0
    status       over | at_limit | near | within | no_budget | no_data
                 "near" uses config.BUDGET.near_threshold_pct (default 80%).

Everything here is an *observation* of recorded transactions, except the
spending-pace projection, which is explicitly labelled as an estimate.
"""

from __future__ import annotations

import calendar
import re
import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd

from src import analytics, config, database
from src.analytics import Filters
from src.money import AmountParseError, format_inr, parse_amount

OVERALL = None  # category value meaning "the overall monthly budget"


class BudgetError(ValueError):
    """User-facing validation problem."""


class DuplicateBudgetError(BudgetError):
    pass


# --------------------------------------------------------------- validation

_MONTH = re.compile(r"^(\d{4})-(\d{2})(?:-01)?$")


def normalize_month(text: str) -> str:
    """'2026-09' or '2026-09-01' → '2026-09-01'."""
    match = _MONTH.match((text or "").strip())
    if not match:
        raise BudgetError("Month must look like 2026-09.")
    year, month = int(match.group(1)), int(match.group(2))
    if not (2000 <= year <= 2100 and 1 <= month <= 12):
        raise BudgetError("That month is out of range.")
    return f"{year:04d}-{month:02d}-01"


def month_bounds(month: str) -> tuple[date, date]:
    start = date.fromisoformat(normalize_month(month))
    return start, start.replace(day=calendar.monthrange(start.year, start.month)[1])


def shift_month(month: str, delta: int) -> str:
    start = date.fromisoformat(normalize_month(month))
    index = start.year * 12 + start.month - 1 + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}-01"


def parse_budget_amount(value) -> int:
    """Rupee text/number → integer paise, validated. Zero is allowed; negatives are not."""
    if isinstance(value, bool):
        raise BudgetError("Enter an amount in rupees.")
    text = str(value).strip() if value is not None else ""
    if text.startswith(("-", "(")):
        raise BudgetError("A budget can't be negative.")
    try:
        paise, _ = parse_amount(text)
    except AmountParseError as exc:
        raise BudgetError("Enter an amount in rupees, e.g. 5000 or 5000.50.") from exc
    if paise > config.BUDGET.max_amount_paise:
        raise BudgetError("That amount is unrealistically large.")
    return paise


def _validate_category(category: str | None) -> str | None:
    if category in (None, "", "__overall__"):
        return OVERALL
    if category not in config.BUDGET_CATEGORIES:
        raise BudgetError(f"“{category}” can't have a spending budget.")
    return category


# ------------------------------------------------------------------- storage

def list_budgets(conn: sqlite3.Connection, month: str) -> list[dict]:
    rows = conn.execute("SELECT * FROM budgets WHERE month = ? ORDER BY category IS NOT NULL, category",
                        (normalize_month(month),)).fetchall()
    return [dict(r) for r in rows]


def get_budget(conn: sqlite3.Connection, budget_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM budgets WHERE id = ?", (budget_id,)).fetchone()
    return dict(row) if row else None


def create_budget(conn: sqlite3.Connection, month: str, category: str | None, amount) -> int:
    month = normalize_month(month)
    category = _validate_category(category)
    paise = parse_budget_amount(amount)
    stamp = database.now_iso()
    try:
        with database.transaction(conn):
            cur = conn.execute(
                "INSERT INTO budgets (month, category, amount_paise, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (month, category, paise, stamp, stamp))
    except sqlite3.IntegrityError as exc:
        if "UNIQUE" in str(exc) or "ux_budget" in str(exc):
            label = category or "the overall budget"
            raise DuplicateBudgetError(f"A budget for {label} already exists for this month. Edit it instead.") from exc
        raise
    return int(cur.lastrowid)


def update_budget(conn: sqlite3.Connection, budget_id: int, amount) -> None:
    paise = parse_budget_amount(amount)
    with database.transaction(conn):
        cur = conn.execute("UPDATE budgets SET amount_paise = ?, updated_at = ? WHERE id = ?",
                           (paise, database.now_iso(), budget_id))
    if cur.rowcount == 0:
        raise BudgetError("Budget not found.")


def delete_budget(conn: sqlite3.Connection, budget_id: int) -> None:
    with database.transaction(conn):
        cur = conn.execute("DELETE FROM budgets WHERE id = ?", (budget_id,))
    if cur.rowcount == 0:
        raise BudgetError("Budget not found.")


def copy_budgets(conn: sqlite3.Connection, from_month: str, to_month: str, overwrite: bool = False) -> dict:
    """Copy every budget from one month to another. Existing budgets in the target
    month are kept unless ``overwrite`` is True."""
    source = list_budgets(conn, from_month)
    target = normalize_month(to_month)
    if normalize_month(from_month) == target:
        raise BudgetError("Choose a different month to copy from.")
    existing = {b["category"]: b for b in list_budgets(conn, target)}
    created = updated = skipped = 0
    stamp = database.now_iso()
    with database.transaction(conn):
        for b in source:
            if b["category"] in existing:
                if overwrite:
                    conn.execute("UPDATE budgets SET amount_paise = ?, updated_at = ? WHERE id = ?",
                                 (b["amount_paise"], stamp, existing[b["category"]]["id"]))
                    updated += 1
                else:
                    skipped += 1
                continue
            conn.execute(
                "INSERT INTO budgets (month, category, amount_paise, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (target, b["category"], b["amount_paise"], stamp, stamp))
            created += 1
    return {"created": created, "updated": updated, "skipped": skipped, "source_count": len(source)}


# ------------------------------------------------------------------ coverage

@dataclass
class Coverage:
    month_start: date
    month_end: date
    covered_from: date | None
    covered_to: date | None

    @property
    def is_covered(self) -> bool:
        return self.covered_from is not None

    @property
    def is_full(self) -> bool:
        return self.is_covered and self.covered_from == self.month_start and self.covered_to == self.month_end

    @property
    def days_in_month(self) -> int:
        return (self.month_end - self.month_start).days + 1

    @property
    def days_covered(self) -> int:
        return (self.covered_to - self.covered_from).days + 1 if self.is_covered else 0

    def as_dict(self) -> dict:
        return {
            "is_covered": self.is_covered, "is_full": self.is_full,
            "covered_from": self.covered_from.isoformat() if self.covered_from else None,
            "covered_to": self.covered_to.isoformat() if self.covered_to else None,
            "days_covered": self.days_covered, "days_in_month": self.days_in_month,
        }


def month_coverage(conn: sqlite3.Connection, month: str) -> Coverage:
    """Which days of the month the imported statements cover (span of all statements,
    the same approximation the monthly summary uses)."""
    start, end = month_bounds(month)
    row = conn.execute("SELECT MIN(statement_period_start), MAX(statement_period_end) FROM statements").fetchone()
    if not row or row[0] is None:
        return Coverage(start, end, None, None)
    span_start, span_end = date.fromisoformat(row[0]), date.fromisoformat(row[1])
    if span_end < start or span_start > end:
        return Coverage(start, end, None, None)
    return Coverage(start, end, max(start, span_start), min(end, span_end))


# ------------------------------------------------------------------- metrics

def pct(numerator: int, denominator: int) -> float | None:
    """numerator / denominator × 100 to 1 dp, rounding halves away from zero — the
    same rule as SQLite's ROUND(), so Python and SQL figures always agree."""
    if not denominator:
        return None
    value = Decimal(100 * numerator) / Decimal(denominator)
    return float(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))

def status_for(budget_paise: int | None, actual_paise: int, covered: bool, near_pct: float | None = None) -> str:
    near_pct = config.BUDGET.near_threshold_pct if near_pct is None else near_pct
    if not covered:
        return "no_data"
    if budget_paise is None:
        return "no_budget"
    if budget_paise == 0:
        return "over" if actual_paise > 0 else "within"
    if actual_paise > budget_paise:
        return "over"
    if actual_paise == budget_paise:
        return "at_limit"
    if 100 * actual_paise / budget_paise >= near_pct:
        return "near"
    return "within"


def _run(conn, name: str, month: str) -> pd.DataFrame:
    start, end = month_bounds(month)
    sql = analytics.load_sql(name)
    return pd.read_sql_query(sql, conn, params={"month_start": start.isoformat(), "month_end": end.isoformat()})


def _pace(actual: int, budget: int | None, cov: Coverage) -> dict | None:
    """Linear spending-pace ESTIMATE for a month whose data starts on day 1 but stops early."""
    settings = config.BUDGET
    if (not cov.is_covered or cov.is_full or cov.covered_from != cov.month_start
            or cov.days_covered < settings.pace_min_days):
        return None
    projected = round(actual * cov.days_in_month / cov.days_covered)
    result = {"is_estimate": True, "days_elapsed": cov.days_covered,
              "days_remaining": cov.days_in_month - cov.days_covered, "projected_paise": projected,
              "expected_to_date_paise": None, "pace": None}
    if budget:
        expected = round(budget * cov.days_covered / cov.days_in_month)
        result["expected_to_date_paise"] = expected
        ratio = 100 * actual / expected if expected else None
        if ratio is not None:
            band = settings.pace_tolerance_pct
            result["pace"] = "faster" if ratio > 100 + band else "slower" if ratio < 100 - band else "on_pace"
            result["pace_pct"] = round(ratio, 1)
    return result


def month_report(conn: sqlite3.Connection, month: str) -> dict:
    """Budget vs actual for one month: category rows, overall row, coverage and pace."""
    month = normalize_month(month)
    cov = month_coverage(conn, month)
    rows_frame = _run(conn, "budget_vs_actual", month)
    overall = _run(conn, "budget_overall", month).iloc[0].to_dict()

    rows = []
    for r in rows_frame.to_dict(orient="records"):
        budget = None if pd.isna(r["budget_paise"]) else int(r["budget_paise"])
        actual = int(r["actual_paise"])
        rows.append({
            "category": r["category"],
            "budget_id": None if pd.isna(r["budget_id"]) else int(r["budget_id"]),
            "budget_paise": budget,
            "actual_paise": actual,
            "transaction_count": int(r["transaction_count"]),
            "remaining_paise": None if budget is None else budget - actual,
            "variance_paise": None if budget is None else actual - budget,
            "utilisation_pct": None if pd.isna(r["utilisation_pct"]) else float(r["utilisation_pct"]),
            "variance_pct": None if pd.isna(r["variance_pct"]) else float(r["variance_pct"]),
            "status": status_for(budget, actual, cov.is_covered),
            "pace": _pace(actual, budget, cov) if budget is not None else None,
        })

    overall_budget = None if pd.isna(overall["overall_budget_paise"]) else int(overall["overall_budget_paise"])
    actual_total = int(overall["expenditure_paise"])
    summary = {
        "overall_budget_id": None if pd.isna(overall["overall_budget_id"]) else int(overall["overall_budget_id"]),
        "overall_budget_paise": overall_budget,
        "category_budgets_paise": int(overall["category_budgets_paise"]),
        "budgeted_category_count": int(overall["budgeted_category_count"]),
        "expenditure_paise": actual_total,
        "refunds_paise": int(overall["refunds_paise"]),
        "net_expenditure_paise": int(overall["net_expenditure_paise"]),
        "unbudgeted_paise": int(overall["unbudgeted_paise"]),
        "remaining_paise": None if overall_budget is None else overall_budget - actual_total,
        "variance_paise": None if overall_budget is None else actual_total - overall_budget,
        "utilisation_pct": pct(actual_total, overall_budget),
        "variance_pct": pct(actual_total - overall_budget, overall_budget) if overall_budget else None,
        "status": status_for(overall_budget, actual_total, cov.is_covered),
        "pace": _pace(actual_total, overall_budget, cov) if overall_budget is not None else None,
    }
    return {"month": month, "coverage": cov.as_dict(), "rows": rows, "overall": summary}


# ------------------------------------------------------------------ insights

def _link(month: str, category: str | None = None) -> dict:
    start, end = month_bounds(month)
    link = {"start": start.isoformat(), "end": end.isoformat(), "types": ["expense"]}
    if category:
        link["categories"] = [category]
    return link


def insights(conn: sqlite3.Connection, month: str, report: dict | None = None) -> list[dict]:
    """Observations about the selected month (and, where noted, earlier months).
    Wording describes what happened; it never judges whether spending was 'bad'."""
    month = normalize_month(month)
    report = report or month_report(conn, month)
    settings = config.BUDGET
    out: list[dict] = []
    if not report["coverage"]["is_covered"]:
        return [{"key": "no_data", "kind": "observed", "tone": "warning", "title": "No statement for this month",
                 "text": "None of your imported statements cover this month, so budgets can't be compared with spending.",
                 "link": None}]
    partial = not report["coverage"]["is_full"]
    so_far = " so far" if partial else ""
    budgeted = [r for r in report["rows"] if r["budget_paise"] is not None]

    overall = report["overall"]
    if overall["overall_budget_paise"] is not None:
        diff = overall["variance_paise"]
        text = (f"Spent {format_inr(overall['expenditure_paise'])}{so_far} against an overall budget of "
                f"{format_inr(overall['overall_budget_paise'])}: "
                + (f"{format_inr(diff)} over." if diff > 0 else "exactly on budget." if diff == 0
                   else f"{format_inr(-diff)} left."))
        out.append({"key": "overall", "kind": "observed", "tone": "up" if diff > 0 else "neutral",
                    "title": "Overall budget", "text": text, "link": _link(month)})

    over = sorted([r for r in budgeted if r["status"] == "over"], key=lambda r: -r["variance_paise"])
    if over:
        names = ", ".join(r["category"] for r in over[:4]) + ("…" if len(over) > 4 else "")
        out.append({"key": "over", "kind": "observed", "tone": "up", "title": f"{len(over)} over budget",
                    "text": f"Spending{so_far} exceeded the budget in {names}.", "link": None})
        top = over[0]
        out.append({"key": "largest_overspend", "kind": "observed", "tone": "up", "title": "Largest overspend",
                    "text": f"{top['category']}: {format_inr(top['actual_paise'])} spent vs {format_inr(top['budget_paise'])} "
                            f"budgeted ({format_inr(top['variance_paise'])} over"
                            + (f", {top['variance_pct']:+.0f}%)." if top["variance_pct"] is not None else ")."),
                    "link": _link(month, top["category"])})

    near = [r for r in budgeted if r["status"] in {"near", "at_limit"}]
    if near:
        out.append({"key": "near", "kind": "observed", "tone": "warning", "title": "Close to the limit",
                    "text": f"{', '.join(r['category'] for r in near)} reached at least {settings.near_threshold_pct:.0f}% "
                            f"of the budget{so_far}.", "link": None})

    unbudgeted = [r for r in report["rows"] if r["budget_paise"] is None]
    if budgeted and unbudgeted:
        total = sum(r["actual_paise"] for r in unbudgeted)
        out.append({"key": "unbudgeted", "kind": "observed", "tone": "neutral", "title": "Spending without a budget",
                    "text": f"{format_inr(total)} went to categories with no budget "
                            f"({', '.join(r['category'] for r in unbudgeted[:4])}{'…' if len(unbudgeted) > 4 else ''}).",
                    "link": None})

    # Utilisation change vs the previous month (only where both months have data and a budget).
    prev_month = shift_month(month, -1)
    prev = month_report(conn, prev_month)
    if prev["coverage"]["is_covered"] and not partial and prev["coverage"]["is_full"]:
        prev_util = {r["category"]: r["utilisation_pct"] for r in prev["rows"] if r["utilisation_pct"] is not None}
        changes = [(r["category"], r["utilisation_pct"] - prev_util[r["category"]])
                   for r in budgeted if r["utilisation_pct"] is not None and r["category"] in prev_util]
        changes = [c for c in changes if abs(c[1]) >= 1]
        if changes:
            biggest = max(changes, key=lambda c: abs(c[1]))
            out.append({"key": "utilisation_change", "kind": "observed", "tone": "up" if biggest[1] > 0 else "down",
                        "title": "Biggest change vs last month",
                        "text": f"{biggest[0]} used {abs(biggest[1]):.0f} percentage points "
                                f"{'more' if biggest[1] > 0 else 'less'} of its budget than in "
                                f"{date.fromisoformat(prev_month).strftime('%B')}.",
                        "link": _link(month, biggest[0])})

    # Repeated overspending across recent complete months with budgets.
    window = [shift_month(month, -i) for i in range(settings.repeat_window_months)]
    reports = [month_report(conn, m) for m in window]
    complete = [r for r in reports if r["coverage"]["is_full"]]
    counts: dict[str, int] = {}
    evaluated: dict[str, int] = {}
    for rep in complete:
        for r in rep["rows"]:
            if r["budget_paise"] is None:
                continue
            evaluated[r["category"]] = evaluated.get(r["category"], 0) + 1
            if r["status"] == "over":
                counts[r["category"]] = counts.get(r["category"], 0) + 1
    repeated = [c for c, n in counts.items() if n >= settings.repeat_min_months and evaluated[c] >= settings.repeat_min_months]
    if repeated:
        out.append({"key": "repeated", "kind": "observed", "tone": "warning", "title": "Repeatedly over budget",
                    "text": f"{', '.join(sorted(repeated))} went over budget in at least {settings.repeat_min_months} of the "
                            f"last {len(complete)} complete months with a budget. The budget may not match how much "
                            "you usually spend there.",
                    "link": None})

    pace = report["overall"].get("pace")
    if pace and pace.get("pace"):
        word = {"faster": "faster than", "slower": "slower than", "on_pace": "roughly in line with"}[pace["pace"]]
        out.append({"key": "pace", "kind": "estimate", "tone": "warning" if pace["pace"] == "faster" else "neutral",
                    "title": "Spending pace (estimate)",
                    "text": f"With data for the first {pace['days_elapsed']} days, spending is running {word} an even pace "
                            f"for the overall budget. If it continued linearly the month would end near "
                            f"{format_inr(pace['projected_paise'])}. This is a projection, not a result.",
                    "link": None})
    return out


# ------------------------------------------------------------------- drivers

def drivers(conn: sqlite3.Connection, month: str, category: str) -> dict:
    """Why is a category where it is? Its merchants this month, and what changed vs last month."""
    start, end = month_bounds(month)
    prev_start, prev_end = month_bounds(shift_month(month, -1))
    f = Filters(start_date=start, end_date=end, categories=(category,))
    merchants = analytics.merchant_stats(conn, f).head(8)
    change = analytics.period_change(conn, "merchant_change", Filters(categories=(category,)),
                                     (start, end), (prev_start, prev_end))
    largest = analytics.largest_transactions(conn, f, limit=5)
    return {"merchants": merchants, "change": change[change["change_paise"] != 0].head(8), "largest": largest}


def history(conn: sqlite3.Connection, month: str, months: int = 6) -> list[dict]:
    """Overall budget vs actual for the selected month and the ones before it."""
    out = []
    for i in reversed(range(months)):
        m = shift_month(month, -i)
        rep = month_report(conn, m)
        if not rep["coverage"]["is_covered"]:
            continue
        o = rep["overall"]
        budget = o["overall_budget_paise"] if o["overall_budget_paise"] is not None else (
            o["category_budgets_paise"] or None)
        out.append({"month": m, "budget_paise": budget,
                    "budget_basis": "overall" if o["overall_budget_paise"] is not None else
                                    ("sum of category budgets" if budget else None),
                    "actual_paise": o["expenditure_paise"], "is_full": rep["coverage"]["is_full"]})
    return out


def default_month(conn: sqlite3.Connection) -> str:
    _, hi = analytics.date_bounds(conn)
    return normalize_month((hi or date.today()).isoformat()[:7])


# --------------------------------------------------------------- demo budgets

DEMO_BUDGETS = {
    "Rent & Housing": "18000", "Groceries": "6500", "Food & Dining": "6000", "Shopping": "8000",
    "Transport": "3000", "Bills & Utilities": "2500", "Subscriptions": "1200", "Entertainment": "1500",
    None: "50000",
}


def seed_demo_budgets(conn: sqlite3.Connection, months=("2026-07", "2026-08", "2026-09")) -> None:
    """Synthetic budgets for the demo dataset (clearly demo-only)."""
    for m in months:
        for category, amount in DEMO_BUDGETS.items():
            try:
                create_budget(conn, m, category, amount)
            except DuplicateBudgetError:
                pass
