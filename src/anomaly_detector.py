"""Interpretable anomaly detection (no machine-learning model).

A payment is flagged as *unusual* when it is unusually large **compared with
similar payments** — the same merchant when it has enough history (its own
history is the best yardstick), otherwise the same category:

    threshold = Q3 + 1.5 × IQR          (Tukey's rule)
    flag if amount > threshold AND amount ≥ 2 × median

The second condition stops categories with a very tight spread (e.g. every
metro ride costs ₹40–₹60) from flagging trivial differences.

Groups with fewer than ``min_observations`` payments are skipped — quartiles
of 3 numbers are meaningless. "Unusual" never means "fraud": the UI says so.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src import config
from src.money import format_inr


@dataclass
class GroupStats:
    count: int
    median: float
    q1: float
    q3: float

    @property
    def iqr(self) -> float:
        return self.q3 - self.q1

    def threshold(self, k: float) -> float:
        return self.q3 + k * self.iqr


def _stats(amounts: pd.Series) -> GroupStats:
    return GroupStats(int(amounts.count()), float(amounts.median()),
                      float(amounts.quantile(0.25)), float(amounts.quantile(0.75)))


def detect_anomalies(transactions: pd.DataFrame, reviews: dict[int, str] | None = None,
                     settings=config.ANOMALY, include_reviewed: bool = False) -> tuple[pd.DataFrame, dict]:
    """``transactions`` needs id, transaction_date, normalized_merchant, category,
    amount_paise, direction, transaction_type.

    Returns (flagged rows, info) where info explains which groups had too little
    history to be checked.
    """
    reviews = reviews or {}
    columns = ["id", "transaction_date", "merchant", "category", "amount_paise", "basis",
               "median_paise", "threshold_paise", "ratio_to_median", "reason", "review_status"]
    info = {"checked_categories": [], "skipped_categories": {}, "checked_merchants": 0}
    if transactions.empty:
        return pd.DataFrame(columns=columns), info

    spend = transactions[(transactions["direction"] == "debit") &
                         (transactions["transaction_type"] == "expense")].copy()
    if spend.empty:
        return pd.DataFrame(columns=columns), info

    category_stats = {}
    for category, group in spend.groupby("category"):
        if len(group) >= settings.min_observations:
            category_stats[category] = _stats(group["amount_paise"])
            info["checked_categories"].append(category)
        else:
            info["skipped_categories"][category] = len(group)

    merchant_stats = {}
    for merchant, group in spend.groupby("normalized_merchant"):
        if len(group) >= settings.merchant_min_observations:
            merchant_stats[merchant] = _stats(group["amount_paise"])
    info["checked_merchants"] = len(merchant_stats)

    flagged = []
    for row in spend.itertuples(index=False):
        # Compare with the most similar payments available: the same merchant if
        # it has enough history, otherwise the same category.
        if row.normalized_merchant in merchant_stats:
            comparison = ("merchant", row.normalized_merchant, merchant_stats[row.normalized_merchant])
        elif row.category in category_stats:
            comparison = ("category", row.category, category_stats[row.category])
        else:
            continue
        for basis, label, stats in [comparison]:
            threshold = stats.threshold(settings.iqr_multiplier)
            if row.amount_paise > threshold and row.amount_paise >= settings.min_ratio_to_median * stats.median:
                ratio = row.amount_paise / stats.median if stats.median else float("inf")
                where = f"your usual {label} payments" if basis == "merchant" else f"your usual {label} spending"
                reason = (f"{format_inr(row.amount_paise)} is {ratio:.1f}× {where} "
                          f"(median {format_inr(stats.median)}, typical upper range ≈ {format_inr(threshold)}, "
                          f"based on {stats.count} payments).")
                flagged.append({
                    "id": int(row.id), "transaction_date": row.transaction_date,
                    "merchant": row.normalized_merchant, "category": row.category,
                    "amount_paise": int(row.amount_paise), "basis": basis,
                    "median_paise": round(stats.median), "threshold_paise": round(threshold),
                    "ratio_to_median": round(ratio, 1), "reason": reason,
                    "review_status": reviews.get(int(row.id), "new"),
                })

    result = pd.DataFrame(flagged, columns=columns)
    if not include_reviewed and not result.empty:
        result = result[result["review_status"] == "new"]
    return result.sort_values("amount_paise", ascending=False).reset_index(drop=True), info
