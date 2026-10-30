"""Interpretable detection of unusually large payments (simple statistics, no ML model).

Only **expenses** are checked (debits classified as spending). Refunds, transfers,
income and card-bill payments are never flagged. Amounts are integer paise and
always > 0 (enforced by the database); anything else is ignored.

Reference distribution ("compared with what?")
    For each payment, the comparison set is the user's **earlier** payments
    (strictly earlier dates, so nothing from the future leaks in):
      1. the same merchant, if it has ≥ ``merchant_min_observations`` earlier payments;
      2. otherwise the same category, if it has ≥ ``min_observations`` earlier payments
         (never the uncategorised "Other" bucket, which mixes unrelated merchants);
      3. otherwise the payment is *not checked* (insufficient history) — it is never
         guessed to be normal or unusual.

Methods (all documented in the README and evaluated in ``src/anomaly_eval.py``)
    rule            amount ≥ a hand-set threshold for its category. No history needed.
                    Baseline only: one number per category can't fit every merchant.
    iqr_full        Tukey's rule on the WHOLE history including the payment itself and
                    later payments (Spendly ≤ 2.1). Kept only as a comparison: it uses
                    future data, so its evaluation is optimistic.
    iqr_prior       amount > Q3 + k × IQR of earlier payments AND ≥ r × their median.
    robust_z_prior  robust z = 0.6745 × (amount − median) ÷ MAD of earlier payments;
                    flag if z ≥ z_threshold AND amount ≥ r × median. (Default.)

    MAD = 0 (e.g. most payments identical): use 1.2533 × mean absolute deviation
    instead (Iglewicz & Hoaglin's fallback). If that is 0 too (all earlier payments
    identical), any different amount has an infinite z, so only the ratio rule
    decides. The ratio rule (amount ≥ 2 × median by default) stops tight
    distributions — every metro ride ₹40–₹60 — from flagging trivial differences.

"Unusual" means unusual *for you*, compared with your own history. It is not a
fraud signal, not a risk score, and nothing is changed automatically.
"""

from __future__ import annotations

import math
from bisect import bisect_left
from functools import cached_property
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src import config
from src.money import format_inr

METHODS = ("rule", "iqr_full", "iqr_prior", "robust_z_prior")
METHOD_LABELS = {
    "rule": "Category threshold rule",
    "iqr_full": "IQR on full history (legacy)",
    "iqr_prior": "IQR on earlier payments",
    "robust_z_prior": "Robust z-score on earlier payments",
}
COLUMNS = ["id", "transaction_date", "merchant", "category", "amount_paise", "method", "basis",
           "reference_label", "reference_count", "median_paise", "q1_paise", "q3_paise", "threshold_paise",
           "mad_paise", "robust_z", "ratio_to_median", "days_since_previous", "deviation", "reason",
           "review_status"]


@dataclass
class Reference:
    basis: str  # merchant | category
    label: str
    amounts: np.ndarray

    @property
    def count(self) -> int:
        return len(self.amounts)

    @cached_property
    def median(self) -> float:
        return float(np.median(self.amounts))

    def quartiles(self) -> tuple[float, float]:
        q1, q3 = np.percentile(self.amounts, [25, 75])  # linear interpolation, same as pandas
        return float(q1), float(q3)

    def robust_scale(self) -> float:
        """Denominator of the robust z (already divided by 0.6745 when using MAD)."""
        med = self.median
        mad = float(np.median(np.abs(self.amounts - med)))
        if mad > 0:
            return mad / 0.6745
        mean_ad = float(np.mean(np.abs(self.amounts - med)))
        return 1.253314 * mean_ad  # 0 when every value is identical

    def mad(self) -> float:
        return float(np.median(np.abs(self.amounts - self.median)))


def robust_z(amount: float, ref: Reference) -> float:
    scale = ref.robust_scale()
    diff = amount - ref.median
    if scale == 0:
        return 0.0 if diff == 0 else math.copysign(math.inf, diff)
    return diff / scale


def deviation_band(z: float | None, ratio: float) -> str:
    """Descriptive size of the deviation (documented bands; not a risk score)."""
    if z is not None and math.isfinite(z):
        return "extreme" if z >= 10 else "large" if z >= 6 else "notable"
    return "extreme" if ratio >= 10 else "large" if ratio >= 4 else "notable"


def expenses(transactions: pd.DataFrame) -> pd.DataFrame:
    if transactions.empty:
        return transactions
    spend = transactions[(transactions["direction"] == "debit") & (transactions["transaction_type"] == "expense")
                         & (transactions["amount_paise"] > 0)].copy()
    spend["transaction_date"] = spend["transaction_date"].astype(str)
    return spend.sort_values(["transaction_date", "id"]).reset_index(drop=True)


def _rule_threshold(category: str, settings) -> int:
    rupees = settings.rule_thresholds.get(category, settings.rule_default_threshold)
    return int(rupees * 100)


def detect_anomalies(transactions: pd.DataFrame, reviews: dict[int, str] | None = None,
                     settings=None, include_reviewed: bool = False, method: str | None = None,
                     params: dict | None = None) -> tuple[pd.DataFrame, dict]:
    """``transactions`` needs id, transaction_date, normalized_merchant, category,
    amount_paise, direction, transaction_type. Pass the FULL history: earlier
    payments are the yardstick, so filtering first would remove the reference.

    Returns (flagged rows, info). ``info`` reports how many payments were checked
    and how many had too little history (per category).
    """
    settings = settings or config.ANOMALY
    method = method or settings.method
    if method not in METHODS:
        raise ValueError(f"Unknown method {method}")
    p = {"iqr_multiplier": settings.iqr_multiplier, "z_threshold": settings.z_threshold,
         "min_ratio_to_median": settings.min_ratio_to_median, **(params or {})}
    reviews = reviews or {}
    info = {"method": method, "method_label": METHOD_LABELS[method], "checked": 0, "insufficient_history": 0,
            "skipped_categories": {}, "checked_categories": [], "checked_merchants": 0,
            "settings": {"merchant_min_observations": settings.merchant_min_observations,
                         "min_observations": settings.min_observations, **p}}
    spend = expenses(transactions)
    if spend.empty:
        return pd.DataFrame(columns=COLUMNS), info

    dates = spend["transaction_date"].to_numpy()
    amounts = spend["amount_paise"].to_numpy(dtype=float)
    merchants = spend["normalized_merchant"].to_numpy()
    categories = spend["category"].to_numpy()

    # Groups keep their rows in date order, so "earlier payments" is a prefix found by bisection.
    groups: dict[tuple[str, str], tuple[list[str], np.ndarray]] = {}
    for kind, keys in (("merchant", merchants), ("category", categories)):
        frame = pd.DataFrame({"k": keys, "d": dates, "a": amounts})
        for key, g in frame.groupby("k", sort=False):
            groups[(kind, key)] = (g["d"].tolist(), g["a"].to_numpy())

    def earlier(kind: str, key: str, day: str) -> np.ndarray:
        ds, am = groups[(kind, key)]
        return am[:bisect_left(ds, day)]

    def reference(i: int) -> Reference | None:
        for kind, key, minimum in (("merchant", merchants[i], settings.merchant_min_observations),
                                   ("category", categories[i], settings.min_observations)):
            # "Other" is a catch-all of unrelated, uncategorised merchants: a ₹42,990 purchase
            # compared with the median of a dozen ₹300 coffees says nothing. Only the
            # merchant's own history counts for those rows.
            if kind == "category" and key == config.UNCATEGORIZED:
                continue
            sample = groups[(kind, key)][1] if method == "iqr_full" else earlier(kind, key, dates[i])
            if len(sample) >= minimum:
                return Reference(kind, key, sample)
        return None

    def days_since_previous(i: int) -> int | None:
        ds = groups[("merchant", merchants[i])][0]
        k = bisect_left(ds, dates[i])
        if k == 0:
            return None
        return (pd.Timestamp(dates[i]) - pd.Timestamp(ds[k - 1])).days

    flagged = []
    merchants_checked: set[str] = set()
    checked_categories: set[str] = set()
    for i in range(len(spend)):
        amount = amounts[i]
        if method == "rule":
            info["checked"] += 1
            checked_categories.add(categories[i])
            threshold = _rule_threshold(categories[i], settings)
            if amount >= threshold:
                reason = (f"{format_inr(amount)} is at or above the {format_inr(threshold)} threshold set for "
                          f"{categories[i]} payments. This rule ignores your own history.")
                flagged.append(_row(spend.iloc[i], method, "rule", categories[i], None, None, None, None,
                                    threshold, None, None, None, days_since_previous(i), "notable", reason, reviews))
            continue

        ref = reference(i)
        if ref is None:
            info["insufficient_history"] += 1
            info["skipped_categories"][categories[i]] = info["skipped_categories"].get(categories[i], 0) + 1
            continue
        info["checked"] += 1
        checked_categories.add(categories[i])
        if ref.basis == "merchant":
            merchants_checked.add(ref.label)
        median = ref.median
        ratio = amount / median if median else math.inf
        big_enough = amount >= p["min_ratio_to_median"] * median
        if not big_enough:
            continue  # both rules also require amount ≥ r × median; skip the costlier statistics
        q1, q3 = ref.quartiles()
        z = robust_z(amount, ref)

        if method in {"iqr_full", "iqr_prior"}:
            threshold = q3 + p["iqr_multiplier"] * (q3 - q1)
            hit = amount > threshold and big_enough
            rule_text = f"above the typical upper range of {format_inr(threshold)} (Q3 + {p['iqr_multiplier']:g} × IQR)"
        else:
            threshold = None
            hit = z >= p["z_threshold"] and big_enough
            z_text = "far above (all were identical)" if math.isinf(z) else f"robust z = {z:.1f}"
            rule_text = f"{z_text}, threshold {p['z_threshold']:g}"
        if hit and ref.basis == "category" and method != "iqr_full":
            # Merchant-consistency guard: a merchant with a short but consistent history
            # (e.g. the 2nd–5th rent payment) isn't unusual just because the category is cheaper.
            own = earlier("merchant", merchants[i], dates[i])
            if len(own) >= settings.merchant_guard_min and amount < p["min_ratio_to_median"] * float(np.median(own)):
                hit = False
        if not hit:
            continue
        when = "earlier " if method != "iqr_full" else ""
        what = f"your {ref.count} {when}payments to {ref.label}" if ref.basis == "merchant" else \
            f"your {ref.count} {when}{ref.label} payments"
        reason = (f"{format_inr(amount)} is {ratio:.1f}× the median of {what} (median {format_inr(median)}, "
                  f"middle half {format_inr(q1)}–{format_inr(q3)}). It is {rule_text} and at least "
                  f"{p['min_ratio_to_median']:g}× the median, so it was flagged as unusual — not as fraud.")
        flagged.append(_row(spend.iloc[i], method, ref.basis, ref.label, ref.count, median, q1, q3, threshold,
                            ref.mad(), z, ratio, days_since_previous(i), deviation_band(z, ratio), reason, reviews))

    info["checked_merchants"] = len(merchants_checked)
    info["checked_categories"] = sorted(checked_categories)
    result = pd.DataFrame(flagged, columns=COLUMNS)
    if not include_reviewed and not result.empty:
        result = result[result["review_status"] == "new"]
    return result.sort_values("amount_paise", ascending=False).reset_index(drop=True), info


def _row(t, method, basis, label, count, median, q1, q3, threshold, mad, z, ratio, days, band, reason, reviews):
    def r(v):
        return None if v is None else round(v)
    return {
        "id": int(t["id"]), "transaction_date": t["transaction_date"], "merchant": t["normalized_merchant"],
        "category": t["category"], "amount_paise": int(t["amount_paise"]), "method": method, "basis": basis,
        "reference_label": label, "reference_count": count, "median_paise": r(median), "q1_paise": r(q1),
        "q3_paise": r(q3), "threshold_paise": r(threshold), "mad_paise": r(mad),
        "robust_z": None if z is None else (None if math.isinf(z) else round(z, 1)),
        "ratio_to_median": None if ratio is None else (None if math.isinf(ratio) else round(ratio, 1)),
        "days_since_previous": days, "deviation": band, "reason": reason,
        "review_status": reviews.get(int(t["id"]), "new"),
    }


def detect_for_view(all_transactions: pd.DataFrame, view: pd.DataFrame | None, reviews: dict[int, str] | None = None,
                    include_reviewed: bool = False) -> tuple[pd.DataFrame, dict]:
    """Detect on the full history, then keep the flags that fall inside the filtered view.
    (Filtering first would shrink the reference history and change the answer.)"""
    flagged, info = detect_anomalies(all_transactions, reviews, include_reviewed=include_reviewed)
    if view is not None and not flagged.empty:
        flagged = flagged[flagged["id"].isin(set(view["id"]))].reset_index(drop=True)
    return flagged, info
