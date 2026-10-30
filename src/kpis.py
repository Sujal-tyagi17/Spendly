"""Executive KPIs and "why did spending change" explanations.

Nothing here defines a new financial metric. Every figure is read from an existing,
tested function (``analytics.totals`` / ``monthly_summary`` / ``category_spending``,
``insights.compare_periods``, ``subscription_detector``, ``budgets.month_report``),
so the Overview, the Insights page and the monthly report show the same numbers.

The KPIs that need a rule of their own are documented here:

average monthly expenditure
    Mean expenditure of the months in view that are *complete*: covered by statements
    from the 1st to the last day, and not cut by the date filter. Partial months are
    excluded, not scaled up. None if there is no complete month.

month-over-month change
    ``insights.compare_periods``: the latest month in view vs the previous one; a
    partial latest month is compared with the same number of days of the previous
    month. None when there is no previous period or it had no spending.

recurring expenditure (estimate)
    Monthly cost of active recurring payments (confirmed or high confidence, not
    stopped), from ``subscription_detector.recurring_monthly_total``. Labelled an estimate.

budget utilisation
    For the latest month in view: expenditure ÷ overall budget × 100, from
    ``budgets.month_report``. If no overall budget exists, utilisation of the sum of
    category budgets is reported instead (and labelled so). None without budgets.
"""

from __future__ import annotations

import calendar
from dataclasses import replace
from datetime import date

import pandas as pd

from src import analytics, budgets, insights, subscription_detector
from src.analytics import Filters
from src.money import format_inr


def _signed(paise: int) -> str:
    return ("+" if paise > 0 else "−" if paise < 0 else "") + format_inr(abs(paise))


def _month_bounds(month_start: date) -> tuple[date, date]:
    return month_start, month_start.replace(day=calendar.monthrange(month_start.year, month_start.month)[1])


def complete_months(conn, filters: Filters) -> pd.DataFrame:
    """Rows of monthly_summary for months that are complete in this view."""
    monthly = analytics.monthly_summary(conn, filters)
    if monthly.empty:
        return monthly
    keep = []
    for row in monthly.itertuples():
        start, end = _month_bounds(date.fromisoformat(str(row.month_start)[:10]))
        inside = (filters.start_date is None or filters.start_date <= start) and \
                 (filters.end_date is None or filters.end_date >= end)
        keep.append(bool(row.is_covered) and bool(row.is_full_month) and inside)
    return monthly[keep]


def executive_summary(conn, filters: Filters | None = None, candidates=None) -> dict:
    filters = filters or Filters()
    totals = analytics.totals(conn, filters)
    full = complete_months(conn, filters)
    comp = insights.compare_periods(conn, filters)
    candidates = subscription_detector.detect_for(conn, filters) if candidates is None else candidates
    active = [c for c in candidates if c.status in {"confirmed", "high_confidence"} and not c.possibly_stopped]

    budget = None
    _, end = analytics.analysis_range(conn, filters)
    if end is not None:
        report = budgets.month_report(conn, end.isoformat()[:7])
        o = report["overall"]
        basis, amount = None, None
        if o["overall_budget_paise"] is not None:
            basis, amount = "overall budget", o["overall_budget_paise"]
        elif o["category_budgets_paise"]:
            basis, amount = "sum of category budgets", o["category_budgets_paise"]
        if basis and report["coverage"]["is_covered"]:
            budget = {
                "month": report["month"], "basis": basis, "budget_paise": amount,
                "actual_paise": o["expenditure_paise"],
                "utilisation_pct": budgets.pct(o["expenditure_paise"], amount),
                "is_full_month": report["coverage"]["is_full"],
                "status": budgets.status_for(amount, o["expenditure_paise"], True),
            }

    return {
        "period": {"start": totals["first_date"], "end": totals["last_date"],
                   "filter_start": filters.start_date.isoformat() if filters.start_date else None,
                   "filter_end": filters.end_date.isoformat() if filters.end_date else None},
        "expenditure_paise": int(totals["expenditure_paise"] or 0),
        "income_paise": int(totals["income_paise"] or 0),
        "net_cash_flow_paise": int(totals["net_cash_flow_paise"] or 0),
        "refunds_paise": int(totals["refunds_paise"] or 0),
        "transaction_count": int(totals["transaction_count"] or 0),
        "average_monthly_expenditure": {
            "value_paise": round(full["expenditure_paise"].mean()) if not full.empty else None,
            "months": int(len(full)),
        },
        "month_over_month": None if comp is None else {
            "current_label": comp.current_label, "previous_label": comp.previous_label,
            "current_paise": comp.current_paise, "previous_paise": comp.previous_paise,
            "change_paise": comp.change_paise, "change_pct": comp.change_pct, "is_partial": comp.is_partial,
        },
        "recurring": {
            "estimated_monthly_paise": subscription_detector.recurring_monthly_total(candidates),
            "active_count": len(active), "is_estimate": True,
        },
        "budget": budget,
    }


# ------------------------------------------------------------ storytelling

def _expense_stats(conn, filters: Filters, period: tuple[date, date]) -> tuple[int, int]:
    """(expense payments, expenditure) in a period, via category_spending (expense rule)."""
    cats = analytics.category_spending(conn, replace(filters, start_date=period[0], end_date=period[1]))
    if cats.empty:
        return 0, 0
    return int(cats["transaction_count"].sum()), int(cats["expenditure_paise"].sum())


def _recurring_spend(conn, filters: Filters, period, merchants: list[str]) -> int:
    if not merchants:
        return 0
    scoped = replace(filters, start_date=period[0], end_date=period[1], merchants=tuple(merchants))
    return int(analytics.totals(conn, scoped)["expenditure_paise"] or 0)


def explain_change(conn, filters: Filters | None = None, candidates=None) -> dict:
    """Why did expenditure change between the latest month in view and the one before?

    Returns ``{"available", "headline", "points": [...], "caveats": [...], "facts"}``.
    Points describe associations in the data (which categories and merchants moved,
    whether there were more payments or bigger ones). They never claim causes.
    """
    filters = filters or Filters()
    comp = insights.compare_periods(conn, filters)
    if comp is None:
        gap = insights.uncovered_previous_month(conn, filters)
        caveat = (f"No imported statement covers {gap}, so there's nothing to compare the latest month with. "
                  f"Import that month's statement to see what changed." if gap
                  else "There's no earlier month inside your imported statements to compare with.")
        return {"available": False, "headline": None, "points": [], "caveats": [caveat], "facts": {}}

    headline = insights.describe_change(comp)
    cur, prev = comp.current_paise, comp.previous_paise
    caveats = []
    if comp.is_partial:
        caveats.append(f"{comp.current_label} is incomplete, so it is compared with the same number of days of the "
                       "previous month, not the whole month.")
    facts = {"current_paise": cur, "previous_paise": prev, "change_paise": comp.change_paise,
             "change_pct": comp.change_pct}
    points: list[dict] = []
    if prev == 0 or cur == prev:
        if prev == 0:
            caveats.append("The previous period had no spending, so there is nothing to break the change down against.")
        return {"available": True, "headline": headline.text, "points": points, "caveats": caveats, "facts": facts,
                "current_label": comp.current_label, "previous_label": comp.previous_label}

    up = cur > prev
    change = comp.change_paise

    def contributors(frame: pd.DataFrame, key: str) -> list[dict]:
        if frame.empty:
            return []
        same_way = frame[frame["change_paise"] > 0] if up else frame[frame["change_paise"] < 0]
        same_way = same_way.reindex(same_way["change_paise"].abs().sort_values(ascending=False).index).head(3)
        return [{"name": r[key], "change_paise": int(r["change_paise"]),
                 "share_of_change_pct": round(100 * r["change_paise"] / change, 1)} for _, r in same_way.iterrows()]

    cats = contributors(comp.categories, "category")
    if cats:
        parts = ", ".join(f"{c['name']} ({_signed(c['change_paise'])})" for c in cats)
        points.append({"key": "categories", "title": "Categories that moved most",
                       "text": f"The largest {'increases' if up else 'decreases'} were in {parts}.", "items": cats})
    merchants = contributors(comp.merchants, "merchant")
    if merchants:
        parts = ", ".join(f"{m['name']} ({_signed(m['change_paise'])})" for m in merchants)
        points.append({"key": "merchants", "title": "Merchants that moved most",
                       "text": f"By merchant: {parts}.", "items": merchants})

    # Frequency vs average size. Exact decomposition:
    #   cur − prev = (n₁ − n₀) × avg₀  +  n₁ × (avg₁ − avg₀)
    n1, s1 = _expense_stats(conn, filters, comp.current)
    n0, s0 = _expense_stats(conn, filters, comp.previous)
    if n0 and n1:
        a0, a1 = s0 / n0, s1 / n1
        count_effect = round((n1 - n0) * a0)
        size_effect = (s1 - s0) - count_effect
        facts.update({"payments_current": n1, "payments_previous": n0, "avg_current_paise": round(a1),
                      "avg_previous_paise": round(a0), "count_effect_paise": count_effect,
                      "size_effect_paise": size_effect})
        more = "more" if n1 > n0 else "fewer" if n1 < n0 else "the same number of"
        bigger = "larger" if a1 > a0 else "smaller" if a1 < a0 else "about the same size"
        dominant = "the number of payments" if abs(count_effect) > abs(size_effect) else "the average payment size"
        points.append({"key": "frequency", "title": "More payments or bigger ones?",
                       "text": f"There were {more} payments ({n0} → {n1}) and the average payment was {bigger} "
                               f"({format_inr(round(a0))} → {format_inr(round(a1))}). Arithmetically, "
                               f"{dominant} accounts for more of the difference "
                               f"({_signed(count_effect)} from the count, "
                               f"{_signed(size_effect)} from the average).",
                       "items": []})

    active = sorted({c.merchant for c in (candidates if candidates is not None else
                                         subscription_detector.detect_for(conn, filters))
                     if c.status in {"confirmed", "high_confidence"} and not c.possibly_stopped})
    if filters.merchants:
        active = [m for m in active if m in set(filters.merchants)]
    if active:
        r1 = _recurring_spend(conn, filters, comp.current, active)
        r0 = _recurring_spend(conn, filters, comp.previous, active)
        facts.update({"recurring_current_paise": r1, "recurring_previous_paise": r0})
        if r1 == r0:
            text = (f"Actually paid to recurring merchants: {format_inr(r1)} in both months, "
                    "so they didn't contribute.")
        else:
            text = (f"Actually paid to recurring merchants went from {format_inr(r0)} to {format_inr(r1)} "
                    f"({_signed(r1 - r0)}), {abs(round(100 * (r1 - r0) / change))}% of the total change.")
        points.append({"key": "recurring", "title": "Recurring payments", "text": text, "items": []})

    caveats.append("These are associations in your transactions, not proven causes.")
    return {"available": True, "headline": headline.text, "points": points, "caveats": caveats, "facts": facts,
            "current_label": comp.current_label, "previous_label": comp.previous_label}
