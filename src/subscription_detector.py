"""Recurring-payment detection.

For every merchant paid at least ``min_occurrences`` times (SQL query
``recurring_candidates.sql`` supplies the payments and the gap in days since
the previous payment), we ask two questions:

1. **Is the timing regular?** What share of the gaps fits a weekly, monthly,
   quarterly or yearly schedule, within a tolerance (monthly = 30 ± 5 days)?
2. **Is the amount stable?** How far does each payment stray from the
   median amount?

Both must hold for a *high-confidence* candidate; weaker evidence gives a
*possible* candidate. Users can confirm or reject a merchant, and that
decision overrides the detector. Cost projections are labelled as estimates.

Exact matches are not required: billing dates drift and prices change.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from src import config
from src.money import format_inr

SUBSCRIPTION_LIKE = {"Subscriptions", "Bills & Utilities", "Healthcare", "Education", "Entertainment"}
# How many payments of each schedule fall in one month (on average).
PAYMENTS_PER_MONTH = {"weekly": 52 / 12, "monthly": 1, "quarterly": 1 / 3, "yearly": 1 / 12}


@dataclass
class Candidate:
    merchant: str
    category: str
    status: str            # confirmed | high_confidence | possible | rejected
    kind: str              # "Subscription / bill" | "Recurring payment"
    schedule: str          # weekly | monthly | quarterly | yearly
    occurrences: int
    median_amount_paise: int
    min_amount_paise: int
    max_amount_paise: int
    est_monthly_paise: int
    est_annual_paise: int
    first_payment: str
    last_payment: str
    next_expected: str
    possibly_stopped: bool
    rationale: str


def _best_schedule(gaps: list[int], settings) -> tuple[str, float]:
    best, best_share = "monthly", -1.0
    for schedule, period in settings.period_days.items():
        tol = settings.interval_tolerance_days[schedule]
        share = sum(1 for g in gaps if abs(g - period) <= tol) / len(gaps)
        if share > best_share:
            best, best_share = schedule, share
    return best, best_share


def detect_recurring(payments: pd.DataFrame, decisions: dict[str, str] | None = None,
                     as_of: date | None = None, settings=config.RECURRING) -> list[Candidate]:
    """``payments``: rows from recurring_candidates.sql. ``as_of``: last date
    covered by the data (used to spot payments that may have stopped)."""
    decisions = decisions or {}
    if payments.empty:
        return []
    as_of = as_of or date.fromisoformat(payments["transaction_date"].max())
    results: list[Candidate] = []

    for merchant, group in payments.groupby("merchant", sort=True):
        group = group.sort_values(["transaction_date", "id"])
        if len(group) < settings.min_occurrences:
            continue
        amounts = [int(a) for a in group["amount_paise"]]
        gaps = [int(g) for g in group["days_since_previous"].dropna()]
        if not gaps or any(g == 0 for g in gaps):
            # Several payments on one day is shopping behaviour, not a bill.
            if decisions.get(merchant) != "confirmed":
                continue
            gaps = [g for g in gaps if g > 0] or [30]

        schedule, interval_share = _best_schedule(gaps, settings)
        median_amount = int(statistics.median(amounts))
        max_dev = max(abs(a - median_amount) for a in amounts) / median_amount if median_amount else 1.0

        if interval_share >= settings.high_confidence_interval_share and max_dev <= settings.high_confidence_amount_tolerance:
            status = "high_confidence"
        elif interval_share >= settings.possible_interval_share and max_dev <= settings.possible_amount_tolerance:
            status = "possible"
        else:
            status = None

        decision = decisions.get(merchant)
        if decision == "confirmed":
            status = "confirmed"
        elif decision == "rejected":
            status = "rejected"
        if status is None:
            continue

        period = settings.period_days[schedule]
        est_monthly = round(median_amount * PAYMENTS_PER_MONTH[schedule])
        last = date.fromisoformat(group["transaction_date"].iloc[-1])
        next_expected = last + timedelta(days=period)
        stopped = (as_of - last).days > period + settings.interval_tolerance_days[schedule]
        category = str(group["category"].mode().iloc[0])

        fits = round(interval_share * len(gaps))
        reasons = [
            f"{len(group)} payments; {fits} of {len(gaps)} gaps match a {schedule} schedule "
            f"(±{settings.interval_tolerance_days[schedule]} days)",
        ]
        if min(amounts) == max(amounts):
            reasons.append(f"same amount every time ({format_inr(median_amount)})")
        else:
            reasons.append(f"amounts {format_inr(min(amounts))}–{format_inr(max(amounts))}, "
                           f"within {max_dev:.0%} of the median")
        if stopped:
            reasons.append(f"no payment since {last.isoformat()} — may have been cancelled")
        if decision:
            reasons.append(f"{decision} by you")

        results.append(Candidate(
            merchant=str(merchant),
            category=category,
            status=status,
            kind="Subscription / bill" if category in SUBSCRIPTION_LIKE else "Recurring payment",
            schedule=schedule,
            occurrences=len(group),
            median_amount_paise=median_amount,
            min_amount_paise=min(amounts),
            max_amount_paise=max(amounts),
            est_monthly_paise=est_monthly,
            est_annual_paise=est_monthly * 12,
            first_payment=group["transaction_date"].iloc[0],
            last_payment=last.isoformat(),
            next_expected=next_expected.isoformat(),
            possibly_stopped=stopped,
            rationale="; ".join(reasons),
        ))

    order = {"confirmed": 0, "high_confidence": 1, "possible": 2, "rejected": 3}
    results.sort(key=lambda c: (order[c.status], -c.est_monthly_paise))
    return results


def to_frame(candidates: list[Candidate]) -> pd.DataFrame:
    return pd.DataFrame([c.__dict__ for c in candidates])


def recurring_monthly_total(candidates: list[Candidate]) -> int:
    """Estimated monthly cost of active (confirmed + high-confidence) payments."""
    return sum(c.est_monthly_paise for c in candidates
               if c.status in {"confirmed", "high_confidence"} and not c.possibly_stopped)
