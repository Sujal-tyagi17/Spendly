"""Reproducible evaluation of the unusual-payment detectors on labelled SYNTHETIC data.

Labels here are *injected* anomalies in generated data. They are not real-world
fraud labels, and good scores on them don't show that the detector would find
fraud, or that real users would agree with every flag.

Dataset (``generate(seed)``), 12 months of one synthetic person's account
    ordinary purchases      ~20 merchants in 10 categories; amounts drawn from a
                            log-normal per merchant (tight: metro, fuel; loose: Amazon)
    repeated transactions   fixed monthly payments (rent, Netflix, Spotify, Airtel) and
                            same-day identical repeats (two coffees)
    large legitimate        a phone, a flight, a medical bill: unusually large but genuine.
                            Labelled NOT anomalous (label 0, kind "legit_large"), because
                            the question is "would the user see a false alarm?"
    refunds, transfers, income, card-bill payments: never eligible (not expenses)
    injected anomalies      label 1:
        inflated        4–12 × the merchant's typical amount
        moderate        2.5–3.5 × the merchant's typical amount (harder)
        new_merchant    a one-off merchant at 5–10 × the category's typical amount
        early           inflated, but in the first 6 weeks (little history yet)
        small_unusual   a tiny payment (₹5–₹30) at a usually expensive merchant.
                        No method here looks for unusually SMALL payments, so these
                        are expected misses; they're kept to show the blind spot.

Temporal split (no random mixing of past and future)
    tune  = Jan–Jun:  parameters are chosen here (grid search, best F1)
    test  = Jul–Dec:  reported results; detectors only ever see earlier payments
    (``iqr_full`` sees all 12 months, including the future: its numbers are optimistic)

Metrics, over eligible payments (expenses) dated in the period
    TP flagged & label 1, FP flagged & label 0, FN not flagged & label 1, TN otherwise.
    Payments with too little history are "not flagged".
    precision = TP / (TP + FP)      None if nothing was flagged
    recall    = TP / (TP + FN)      None if there were no anomalies
    F1        = 2PR / (P + R)       None if P or R is None; 0 if P + R = 0
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from statistics import mean, pstdev

import numpy as np
import pandas as pd

from src import config
from src.anomaly_detector import detect_anomalies

YEAR = 2025
TUNE = (f"{YEAR}-01-01", f"{YEAR}-06-30")
TEST = (f"{YEAR}-07-01", f"{YEAR}-12-31")

# merchant, category, median ₹, log-sd, payments per month
MERCHANTS = [
    ("Zomato", "Food & Dining", 450, 0.35, 9), ("Swiggy", "Food & Dining", 400, 0.35, 7),
    ("Third Wave Coffee", "Food & Dining", 260, 0.2, 5),
    ("Blinkit", "Groceries", 700, 0.45, 6), ("BigBasket", "Groceries", 1800, 0.3, 2),
    ("Sharma Kirana", "Groceries", 300, 0.5, 5),
    ("Uber", "Transport", 280, 0.4, 7), ("Delhi Metro", "Transport", 50, 0.08, 18),
    ("Indian Oil", "Transport", 1500, 0.15, 3),
    ("Amazon", "Shopping", 1200, 0.9, 3), ("Myntra", "Shopping", 1600, 0.6, 1),
    ("BookMyShow", "Entertainment", 600, 0.3, 1.5),
    ("Electricity Board", "Bills & Utilities", 1800, 0.25, 1),
    ("Apollo Pharmacy", "Healthcare", 400, 0.5, 1.2),
    ("IRCTC", "Travel", 1200, 0.5, 0.6),
]
FIXED = [("Landlord", "Rent & Housing", 18000, 1), ("Netflix", "Subscriptions", 649, 5),
         ("Spotify", "Subscriptions", 119, 7), ("Airtel", "Bills & Utilities", 599, 12)]
LEGIT_LARGE = [("Amazon", "Shopping", 34999, "03-14"), ("IRCTC", "Travel", 9800, "05-02"),
               ("Apollo Pharmacy", "Healthcare", 7200, "08-19"), ("Croma", "Shopping", 45999, "10-23"),
               ("MakeMyTrip", "Travel", 18500, "11-30")]


def _lognormal(rng: random.Random, median: float, sd: float) -> int:
    return max(100, int(round(median * np.exp(rng.gauss(0, sd)) * 100)))


def generate(seed: int = 42) -> pd.DataFrame:
    rng = random.Random(seed)
    rows: list[dict] = []

    def add(day: date, merchant, category, paise, *, direction="debit", ttype="expense", label=0, kind="ordinary"):
        rows.append({"transaction_date": day.isoformat(), "normalized_merchant": merchant, "category": category,
                     "amount_paise": int(paise), "direction": direction, "transaction_type": ttype,
                     "label": label, "label_kind": kind})

    for month in range(1, 13):
        days = (date(YEAR + (month == 12), month % 12 + 1, 1) - timedelta(days=1)).day
        for merchant, category, median, sd, rate in MERCHANTS:
            n = np.random.default_rng(rng.randrange(1 << 30)).poisson(rate)
            for _ in range(n):
                add(date(YEAR, month, rng.randint(1, days)), merchant, category, _lognormal(rng, median, sd))
        for merchant, category, amount, dom in FIXED:
            add(date(YEAR, month, dom), merchant, category, amount * 100, kind="repeated_fixed")
        add(date(YEAR, month, 1), "Acme Salary", "Income", 85_000_00, direction="credit", ttype="income", kind="income")
        add(date(YEAR, month, rng.randint(3, 25)), "Self transfer", "Transfers", rng.randint(5, 40) * 1000_00,
            ttype="transfer", kind="transfer")
        add(date(YEAR, month, 20), "Card bill", "Transfers", rng.randint(8, 25) * 1000_00, ttype="cc_repayment",
            kind="transfer")
        if rng.random() < 0.6:
            add(date(YEAR, month, rng.randint(1, days)), "Amazon", "Refunds", rng.randint(2, 30) * 100_00,
                direction="credit", ttype="refund", kind="refund")
        # same-day identical repeat (two coffees)
        d = date(YEAR, month, rng.randint(1, days))
        amt = _lognormal(rng, 260, 0.1)
        add(d, "Third Wave Coffee", "Food & Dining", amt, kind="repeated_same_day")
        add(d, "Third Wave Coffee", "Food & Dining", amt, kind="repeated_same_day")

    for merchant, category, rupees, mmdd in LEGIT_LARGE:
        add(date.fromisoformat(f"{YEAR}-{mmdd}"), merchant, category, rupees * 100, kind="legit_large")

    variable = [m for m in MERCHANTS if m[4] >= 2]

    def inject(kind, count, months, factor):
        for _ in range(count):
            merchant, category, median, _, _ = rng.choice(variable)
            m = rng.choice(months)
            day = date(YEAR, m, rng.randint(1, 28))
            add(day, merchant, category, int(median * rng.uniform(*factor) * 100), label=1, kind=kind)

    inject("inflated", 26, range(3, 13), (4, 12))
    inject("moderate", 14, range(3, 13), (2.5, 3.5))
    inject("early", 4, [1], (4, 12))
    for _ in range(8):
        merchant, category, median, _, _ = rng.choice(variable)
        m = rng.randint(3, 12)
        add(date(YEAR, m, rng.randint(1, 28)), f"One-off {category} store {rng.randint(1, 999)}", category,
            int(median * rng.uniform(5, 10) * 100), label=1, kind="new_merchant")
    for _ in range(6):
        merchant, category = rng.choice([("BigBasket", "Groceries"), ("Indian Oil", "Transport"),
                                         ("Electricity Board", "Bills & Utilities")])
        add(date(YEAR, rng.randint(3, 12), rng.randint(1, 28)), merchant, category, rng.randint(5, 30) * 100,
            label=1, kind="small_unusual")

    frame = pd.DataFrame(rows).sort_values(["transaction_date", "normalized_merchant", "amount_paise"],
                                           kind="mergesort").reset_index(drop=True)
    frame.insert(0, "id", range(1, len(frame) + 1))
    return frame


# ------------------------------------------------------------------ metrics

@dataclass
class Confusion:
    tp: int
    fp: int
    tn: int
    fn: int

    @property
    def precision(self) -> float | None:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else None

    @property
    def recall(self) -> float | None:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else None

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if p is None or r is None:
            return None
        return 0.0 if p + r == 0 else 2 * p * r / (p + r)

    def as_dict(self) -> dict:
        def r(v):
            return None if v is None else round(v, 3)
        return {"tp": self.tp, "fp": self.fp, "tn": self.tn, "fn": self.fn,
                "precision": r(self.precision), "recall": r(self.recall), "f1": r(self.f1)}


def confusion(labels: pd.Series, flagged: pd.Series) -> Confusion:
    labels, flagged = labels.astype(bool), flagged.astype(bool)
    return Confusion(int((labels & flagged).sum()), int((~labels & flagged).sum()),
                     int((~labels & ~flagged).sum()), int((labels & ~flagged).sum()))


def run(frame: pd.DataFrame, method: str, period: tuple[str, str], params: dict | None = None) -> dict:
    """Detect over the whole frame (detectors only use earlier payments themselves),
    then score the eligible payments dated inside ``period``."""
    history = frame[frame["transaction_date"] <= period[1]]
    flagged, info = detect_anomalies(history, include_reviewed=True, method=method, params=params)
    ids = set(flagged["id"])
    eligible = history[(history["direction"] == "debit") & (history["transaction_type"] == "expense")
                       & (history["transaction_date"] >= period[0])]
    hits = eligible["id"].isin(ids)
    by_kind = {}
    for kind, g in eligible.groupby("label_kind"):
        by_kind[kind] = {"count": len(g), "flagged": int(g["id"].isin(ids).sum())}
    non_expense_flagged = int(history[~((history["direction"] == "debit")
                                        & (history["transaction_type"] == "expense"))]["id"].isin(ids).sum())
    return {"method": method, "params": params or {}, "period": period, "eligible": len(eligible),
            "anomalies": int(eligible["label"].sum()), **confusion(eligible["label"], hits).as_dict(),
            "by_kind": by_kind, "not_checked": int(info["insufficient_history"]),
            "non_expense_flagged": non_expense_flagged}


GRID = {
    "iqr_prior": [{"iqr_multiplier": k, "min_ratio_to_median": r} for k in (1.5, 2.0, 3.0) for r in (1.5, 2.0, 3.0)],
    "robust_z_prior": [{"z_threshold": z, "min_ratio_to_median": r} for z in (3.0, 3.5, 5.0) for r in (1.5, 2.0, 3.0)],
}


def _defaults(method: str) -> dict:
    s = config.ANOMALY
    if method in {"iqr_prior", "iqr_full"}:
        return {"iqr_multiplier": s.iqr_multiplier, "min_ratio_to_median": s.min_ratio_to_median}
    if method == "robust_z_prior":
        return {"z_threshold": s.z_threshold, "min_ratio_to_median": s.min_ratio_to_median}
    return {}


def tune(frame: pd.DataFrame, method: str) -> tuple[dict, list[dict]]:
    """Pick parameters by F1 on the tuning period only (ties → the more conservative)."""
    trials = [run(frame, method, TUNE, p) for p in GRID[method]]
    best = max(trials, key=lambda t: (t["f1"] or 0, t["precision"] or 0))
    return best["params"], trials


@lru_cache(maxsize=4)
def evaluate(seed: int = 42, seeds: tuple[int, ...] = (1, 2, 3, 4, 5)) -> dict:
    frame = generate(seed)
    results = []
    for method in ("rule", "iqr_full", "iqr_prior", "robust_z_prior"):
        default = _defaults(method)
        entry = {"method": method, "default_params": default,
                 "tune_default": run(frame, method, TUNE, default),
                 "test_default": run(frame, method, TEST, default)}
        if method in GRID:
            best, trials = tune(frame, method)
            entry["tuned_params"] = best
            entry["test_tuned"] = run(frame, method, TEST, best)
            entry["grid"] = [{"params": t["params"], "f1": t["f1"], "precision": t["precision"], "recall": t["recall"]}
                             for t in trials]
        # Stability: default parameters on other seeds' test halves.
        per_seed = [run(generate(s), method, TEST, default) for s in seeds]
        entry["seeds"] = {k: _spread([r[k] for r in per_seed]) for k in ("precision", "recall", "f1")}
        results.append(entry)
    labels = frame[(frame["direction"] == "debit") & (frame["transaction_type"] == "expense")]
    return {
        "seed": seed, "stability_seeds": list(seeds), "tune_period": TUNE, "test_period": TEST,
        "dataset": {"rows": len(frame), "eligible_expenses": len(labels), "anomalies": int(labels["label"].sum()),
                    "by_kind": labels.groupby("label_kind").size().to_dict(),
                    "non_expense_rows": int(len(frame) - len(labels))},
        "results": results,
    }


def _spread(values):
    vals = [v for v in values if v is not None]
    return {"mean": round(mean(vals), 3) if vals else None, "sd": round(pstdev(vals), 3) if len(vals) > 1 else None,
            "n": len(vals)}
