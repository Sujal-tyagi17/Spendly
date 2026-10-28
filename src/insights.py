"""Spending intelligence: explains *why* spending changed, using only numbers
computed by the SQL engine.

Comparison rule
---------------
The current period is the latest month in view. If that month is complete,
it is compared with the whole previous month. If it is partial (data stops
on the 12th), it is compared with the first 12 days of the previous month,
so both periods have equal length, and it is labelled as partial.

When the previous period had no spending, no percentage is shown ("spending
began this period") — dividing by zero is never presented as +∞%.

Insights are generated from templates (deterministic). The optional AI layer
may only *rephrase* them and is validated against these facts.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from src import analytics, database
from src.analytics import Filters
from src.money import format_inr


@dataclass
class PeriodComparison:
    current: tuple[date, date]
    previous: tuple[date, date]
    is_partial: bool
    current_paise: int
    previous_paise: int
    categories: pd.DataFrame
    merchants: pd.DataFrame

    @property
    def change_paise(self) -> int:
        return self.current_paise - self.previous_paise

    @property
    def change_pct(self) -> float | None:
        if self.previous_paise <= 0:
            return None
        return round(100 * self.change_paise / self.previous_paise, 1)

    @property
    def current_label(self) -> str:
        start, end = self.current
        if self.is_partial:
            return f"{start.strftime('%b')} 1–{end.day}, {end.year} (partial month)"
        return start.strftime("%B %Y")

    @property
    def previous_label(self) -> str:
        start, end = self.previous
        if self.is_partial:
            return f"{start.strftime('%b')} 1–{end.day}, {end.year}"
        return start.strftime("%B %Y")


@dataclass
class Insight:
    key: str
    title: str
    text: str
    tone: str = "neutral"  # neutral | up | down | warning | good
    facts: dict = field(default_factory=dict)


def _month_end(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def comparison_periods(analysis_end: date) -> tuple[tuple[date, date], tuple[date, date], bool]:
    cur_start = analysis_end.replace(day=1)
    is_partial = analysis_end != _month_end(analysis_end)
    prev_start = (cur_start - timedelta(days=1)).replace(day=1)
    prev_month_end = _month_end(prev_start)
    if is_partial:
        prev_end = min(prev_start + timedelta(days=analysis_end.day - 1), prev_month_end)
    else:
        prev_end = prev_month_end
    return (cur_start, analysis_end), (prev_start, prev_end), is_partial


def compare_periods(conn, filters: Filters | None = None) -> PeriodComparison | None:
    """Latest month in view vs the previous one. None if there is not enough data."""
    filters = filters or Filters()
    data_start, data_end = analytics.date_bounds(conn)
    if data_end is None:
        return None
    cov_start, cov_end = database.coverage_period(conn)
    coverage_start = date.fromisoformat(cov_start) if cov_start else data_start
    coverage_end = date.fromisoformat(cov_end) if cov_end else data_end

    analysis_end = min(filters.end_date or coverage_end, coverage_end)
    current, previous, is_partial = comparison_periods(analysis_end)
    if previous[0] < coverage_start.replace(day=1) or previous[1] < coverage_start:
        return None  # no previous period inside the uploaded statements

    categories = analytics.period_change(conn, "category_change", filters, current, previous)
    merchants = analytics.period_change(conn, "merchant_change", filters, current, previous)
    return PeriodComparison(
        current=current,
        previous=previous,
        is_partial=is_partial,
        current_paise=int(categories["current_paise"].sum()) if not categories.empty else 0,
        previous_paise=int(categories["previous_paise"].sum()) if not categories.empty else 0,
        categories=categories,
        merchants=merchants,
    )


def describe_change(comp: PeriodComparison) -> Insight:
    cur, prev = comp.current_paise, comp.previous_paise
    facts = {"current_paise": cur, "previous_paise": prev, "change_pct": comp.change_pct,
             "current_period": comp.current_label, "previous_period": comp.previous_label}
    if cur == 0 and prev == 0:
        return Insight("overall_change", "No spending to compare",
                       f"There was no expenditure in {comp.current_label} or {comp.previous_label}.", facts=facts)
    if prev == 0:
        return Insight("overall_change", "Spending began this period",
                       f"You spent {format_inr(cur)} in {comp.current_label}; there was no expenditure in "
                       f"{comp.previous_label}, so a percentage change isn't meaningful.", "up", facts)

    direction = "increased" if cur > prev else "decreased" if cur < prev else "stayed the same"
    text = (f"Your expenditure {direction} by {abs(comp.change_pct):.1f}% "
            f"({format_inr(prev)} → {format_inr(cur)}) in {comp.current_label} compared with {comp.previous_label}.")
    if cur == prev:
        text = f"Your expenditure was the same ({format_inr(cur)}) in {comp.current_label} and {comp.previous_label}."

    cats = comp.categories
    if cur > prev and not cats.empty and cats["change_paise"].max() > 0:
        top = cats.sort_values("change_paise", ascending=False).iloc[0]
        share = 100 * top["change_paise"] / comp.change_paise
        text += f" {top['category']} contributed the largest share of the increase (+{format_inr(top['change_paise'])}"
        text += f", {share:.0f}% of it)." if share <= 100 else ")."
        facts["top_driver"] = top["category"]
    elif cur < prev and not cats.empty and cats["change_paise"].min() < 0:
        top = cats.sort_values("change_paise").iloc[0]
        text += f" The biggest drop was in {top['category']} (−{format_inr(abs(top['change_paise']))})."
        facts["top_driver"] = top["category"]
    tone = "up" if cur > prev else "down" if cur < prev else "neutral"
    return Insight("overall_change", "Change vs previous period", text, tone, facts)


def build_insights(conn, filters: Filters | None = None, recurring=None, anomalies: pd.DataFrame | None = None) -> list[Insight]:
    """All deterministic insight templates, in display order."""
    filters = filters or Filters()
    insights: list[Insight] = []
    totals = analytics.totals(conn, filters)
    if not totals["transaction_count"]:
        return insights

    comp = compare_periods(conn, filters)
    if comp is not None:
        insights.append(describe_change(comp))
        cats = comp.categories
        if not cats.empty:
            inc = cats[cats["change_paise"] > 0]
            if not inc.empty:
                r = inc.iloc[0]
                pct = f" ({r['change_pct']:+.0f}%)" if pd.notna(r["change_pct"]) else " (new this period)"
                insights.append(Insight("biggest_increase", "Biggest increase",
                                        f"{r['category']} rose by {format_inr(r['change_paise'])}{pct}.", "up",
                                        {"category": r["category"], "change_paise": int(r["change_paise"])}))
            dec = cats[cats["change_paise"] < 0].sort_values("change_paise")
            if not dec.empty:
                r = dec.iloc[0]
                insights.append(Insight("biggest_decrease", "Biggest decrease",
                                        f"{r['category']} fell by {format_inr(abs(r['change_paise']))}"
                                        f" ({r['change_pct']:+.0f}%).", "down",
                                        {"category": r["category"], "change_paise": int(r["change_paise"])}))

    cats_all = analytics.category_spending(conn, filters)
    if not cats_all.empty:
        r = cats_all.iloc[0]
        insights.append(Insight("largest_category", "Largest category",
                                f"{r['category']} is your largest spending category: {format_inr(r['expenditure_paise'])}"
                                f" ({r['share_pct']:.0f}% of expenditure).", facts={"category": r["category"]}))

    weekdays = analytics.weekday_spending(conn, filters)
    if not weekdays.empty and weekdays["expenditure_paise"].sum() > 0:
        r = weekdays.sort_values("expenditure_paise", ascending=False).iloc[0]
        insights.append(Insight("top_weekday", "Highest-spending weekday",
                                f"You spend the most on {r['weekday_name']}s: {format_inr(r['expenditure_paise'])} "
                                f"across {int(r['transaction_count'])} payments.", facts={"weekday": r["weekday_name"]}))

    largest = analytics.largest_transactions(conn, filters, limit=1)
    if not largest.empty:
        r = largest.iloc[0]
        insights.append(Insight("largest_transaction", "Largest payment",
                                f"Your largest payment was {format_inr(r['amount_paise'])} to {r['merchant']} "
                                f"on {r['transaction_date']}.", facts={"id": int(r["id"])}))

    if recurring:
        from src.subscription_detector import recurring_monthly_total
        active = [c for c in recurring if c.status in {"confirmed", "high_confidence"} and not c.possibly_stopped]
        if active:
            monthly = recurring_monthly_total(recurring)
            insights.append(Insight("recurring", "Recurring payments",
                                    f"{len(active)} recurring payments cost about {format_inr(monthly)} a month "
                                    f"(≈ {format_inr(monthly * 12)} a year, estimated).", facts={"count": len(active)}))

    if totals["uncategorized_count"]:
        insights.append(Insight("uncategorized", "Needs categories",
                                f"{int(totals['uncategorized_count'])} transactions "
                                f"({format_inr(totals['uncategorized_debits_paise'])} of debits) are uncategorized. "
                                "Fix them on the Transactions page to sharpen every chart.", "warning"))

    if anomalies is not None and not anomalies.empty:
        insights.append(Insight("unusual", "Unusual payments",
                                f"{len(anomalies)} payment(s) are much larger than your usual spending at the same "
                                "merchant or in the same category. Unusual doesn't mean fraudulent — review them on "
                                "the Spending Insights page.", "warning"))
    return insights
