"""Unusual-payment detection: behaviour, edge cases, leakage and the labelled evaluation."""

import json
import math

import numpy as np
import pandas as pd
import pytest

from src import analytics, anomaly_eval, config, database
from src.anomaly_detector import Reference, detect_anomalies, detect_for_view, robust_z
from src.anomaly_eval import Confusion, confusion


def frame(amounts_by_category: dict[str, list[int]], merchant_for=lambda cat, i: f"{cat} shop {i}",
          start_day: int = 1):
    """One payment per day in list order, so 'earlier' means earlier in the list."""
    rows, next_id = [], 1
    for category, amounts in amounts_by_category.items():
        for i, amount in enumerate(amounts):
            day = pd.Timestamp("2026-01-01") + pd.Timedelta(days=start_day - 1 + i)
            rows.append({"id": next_id, "transaction_date": day.date().isoformat(),
                         "normalized_merchant": merchant_for(category, i), "category": category,
                         "amount_paise": amount * 100, "direction": "debit", "transaction_type": "expense"})
            next_id += 1
    return pd.DataFrame(rows)


FOOD = [300, 320, 280, 350, 310, 290, 330, 300, 340]  # 9 ordinary payments


# ------------------------------------------------------------------ behaviour

def test_typical_transactions_are_not_flagged():
    flagged, info = detect_anomalies(frame({"Food & Dining": FOOD + [310, 305]}))
    assert flagged.empty
    assert info["checked"] == 3 and info["insufficient_history"] == 8   # first 8 have < 8 earlier payments


def test_outlier_is_flagged_with_full_explanation():
    flagged, _ = detect_anomalies(frame({"Food & Dining": FOOD + [2800]}))
    assert len(flagged) == 1
    row = flagged.iloc[0]
    # Hand-computed reference: the 9 earlier payments.
    median = 310.0
    mad = float(np.median(np.abs(np.array(FOOD) - median)))   # |dev| = 10,10,30,40,0,20,20,10,30 → 20
    assert mad == 20
    assert row["median_paise"] == 310_00 and row["mad_paise"] == 20_00
    assert row["robust_z"] == round(0.6745 * (2800 - 310) / 20, 1)
    assert row["ratio_to_median"] == round(2800 / 310, 1)
    assert row["basis"] == "category" and row["reference_count"] == 9 and row["method"] == "robust_z_prior"
    assert row["deviation"] == "extreme"
    for part in ("₹2,800", "9 earlier Food & Dining payments", "median ₹310", "robust z", "not as fraud"):
        assert part in row["reason"]


def test_very_small_dataset_is_not_checked():
    flagged, info = detect_anomalies(frame({"Travel": [500, 600, 50_000]}))
    assert flagged.empty
    assert info["checked"] == 0 and info["skipped_categories"] == {"Travel": 3}


def test_missing_history_for_early_payment():
    # The outlier comes FIRST: there's nothing earlier to compare it with.
    flagged, info = detect_anomalies(frame({"Food & Dining": [2800] + FOOD}))
    assert flagged.empty and info["insufficient_history"] == 8  # the 10th row has 9 earlier payments


def test_constant_amounts():
    # MAD = 0 and mean AD = 0: any different amount has infinite z; the ratio rule decides.
    constant = [649] * 8
    assert detect_anomalies(frame({"Subscriptions": constant + [650]}))[0].empty       # 1.0× median
    flagged, _ = detect_anomalies(frame({"Subscriptions": constant + [1999]}))         # 3.1× median
    assert len(flagged) == 1 and flagged.iloc[0]["robust_z"] is None                  # z = ∞, not shown as a number
    assert "all were identical" in flagged.iloc[0]["reason"]


def test_mad_zero_falls_back_to_mean_absolute_deviation():
    ref = Reference("category", "x", np.array([100, 100, 100, 100, 100, 100, 100, 160], dtype=float))
    # MAD = 0; mean AD = 60/8 = 7.5; scale = 1.253314 × 7.5
    assert robust_z(400, ref) == pytest.approx(300 / (1.253314 * 7.5))
    assert robust_z(100, Reference("c", "x", np.array([100.0] * 5))) == 0
    assert math.isinf(robust_z(101, Reference("c", "x", np.array([100.0] * 5))))


def test_comparison_is_category_specific():
    data = frame({"Groceries": [1500, 1700, 1800, 1600, 1750, 1650, 1550, 1800, 1700, 1650],
                  "Transport": [60, 80, 70, 90, 65, 75, 85, 70, 80, 1800]})
    flagged, _ = detect_anomalies(data)
    assert list(flagged["category"]) == ["Transport"]


def test_merchant_history_preferred_and_consistency_guard():
    # Rent ₹18,000 in "Other" next to ₹100 purchases. The first rent payment is unusual for the
    # category; the 2nd onward match the landlord's own earlier payments, so they aren't flagged.
    amounts = [100, 120, 90, 110, 130, 95, 105, 115, 18000, 18000, 18000, 18000, 18000, 18000, 18000]
    flagged, _ = detect_anomalies(frame({"Other": amounts}, merchant_for=lambda c, i: "Landlord" if i >= 8 else f"Shop {i}"))
    assert len(flagged) == 1 and flagged.iloc[0]["merchant"] == "Landlord"
    assert flagged.iloc[0]["transaction_date"] == "2026-01-09"  # only the first one


def test_tight_spread_does_not_flag_tiny_differences():
    flagged, _ = detect_anomalies(frame({"Transport": [40, 42, 38, 40, 41, 39, 40, 40, 60]}))
    assert flagged.empty  # z is large, but 60 < 2 × median (40)


def test_legitimate_large_purchase_is_flagged_but_not_called_fraud():
    flagged, _ = detect_anomalies(frame({"Shopping": [800, 1200, 950, 1500, 700, 1100, 1300, 900, 54_999]}))
    assert len(flagged) == 1
    assert "fraud" not in flagged.iloc[0]["reason"].replace("not as fraud", "")


def test_refunds_transfers_and_income_never_flagged():
    data = frame({"Food & Dining": FOOD})
    extra = pd.DataFrame([
        {"id": 100, "transaction_date": "2026-02-01", "normalized_merchant": "Food & Dining shop 1", "category": "Refunds",
         "amount_paise": 9_000_00, "direction": "credit", "transaction_type": "refund"},
        {"id": 101, "transaction_date": "2026-02-01", "normalized_merchant": "Self", "category": "Transfers",
         "amount_paise": 50_000_00, "direction": "debit", "transaction_type": "transfer"},
        {"id": 102, "transaction_date": "2026-02-01", "normalized_merchant": "Acme", "category": "Income",
         "amount_paise": 90_000_00, "direction": "credit", "transaction_type": "income"},
    ])
    flagged, info = detect_anomalies(pd.concat([data, extra]))
    assert flagged.empty and info["checked"] + info["insufficient_history"] == len(FOOD)


def test_zero_or_negative_amounts_are_ignored():
    data = frame({"Food & Dining": FOOD + [0, -500]})
    flagged, info = detect_anomalies(data)
    assert flagged.empty and info["checked"] + info["insufficient_history"] == len(FOOD)


def test_sparse_category_with_merchant_history():
    # Only 6 Healthcare payments (category needs 8), but the pharmacy itself has 5 earlier ones.
    flagged, _ = detect_anomalies(frame({"Healthcare": [400, 420, 380, 410, 390, 4000]},
                                        merchant_for=lambda c, i: "Apollo Pharmacy"))
    assert len(flagged) == 1 and flagged.iloc[0]["basis"] == "merchant"


def test_duplicate_payments_are_not_unusual():
    flagged, _ = detect_anomalies(frame({"Food & Dining": FOOD + [300, 300, 300]}))
    assert flagged.empty


def test_no_temporal_leakage():
    """Adding FUTURE payments must not change the verdict on an earlier one."""
    base = frame({"Food & Dining": FOOD + [900]})
    before, _ = detect_anomalies(base)
    future = frame({"Food & Dining": [5000, 6000, 7000, 8000, 9000]}, start_day=40)
    future["id"] += 1000
    after, _ = detect_anomalies(pd.concat([base, future]))
    day = base.iloc[-1]["transaction_date"]
    assert list(before[before.transaction_date == day]["robust_z"]) == list(after[after.transaction_date == day]["robust_z"])
    assert len(before) == 1
    # The legacy full-history method DOES change, which is exactly the leakage being removed.
    legacy_before, _ = detect_anomalies(base, method="iqr_full")
    legacy_after, _ = detect_anomalies(pd.concat([base, future]), method="iqr_full")
    assert 10 in set(legacy_before["id"]) and 10 not in set(legacy_after["id"])


def test_view_filter_does_not_shrink_history():
    data = frame({"Food & Dining": FOOD + [2800]})
    only_last = data[data["id"] == 10]
    flagged, _ = detect_for_view(data, only_last)
    assert list(flagged["id"]) == [10]
    alone, _ = detect_anomalies(only_last)        # what the old code effectively did
    assert alone.empty


@pytest.mark.parametrize("method", ["rule", "iqr_full", "iqr_prior", "robust_z_prior"])
def test_every_method_runs_and_explains(method):
    flagged, info = detect_anomalies(frame({"Food & Dining": FOOD + [2800, 3500]}), method=method)
    assert info["method"] == method and len(flagged) >= 1
    assert all(isinstance(r, str) and len(r) > 30 for r in flagged["reason"])


def test_unknown_method():
    with pytest.raises(ValueError):
        detect_anomalies(frame({"Food & Dining": FOOD}), method="isolation_forest")


def test_empty_input():
    flagged, info = detect_anomalies(pd.DataFrame())
    assert flagged.empty and info["checked"] == 0


def test_dismissed_alerts_do_not_return(demo_conn):
    txns = analytics.transactions(demo_conn)
    flagged, _ = detect_anomalies(txns, database.anomaly_reviews(demo_conn))
    first = int(flagged.iloc[0]["id"])
    database.set_anomaly_review(demo_conn, first, "dismissed")
    again, _ = detect_anomalies(txns, database.anomaly_reviews(demo_conn))
    assert first not in set(again["id"])
    with_reviewed, _ = detect_anomalies(txns, database.anomaly_reviews(demo_conn), include_reviewed=True)
    assert first in set(with_reviewed["id"])
    # Reviewing never changes the transaction itself.
    assert database.get_transaction(demo_conn, first)["category"] == "Shopping"


def test_demo_laptop_purchase_is_flagged(demo_conn):
    flagged, _ = detect_anomalies(analytics.transactions(demo_conn))
    top = flagged.iloc[0]
    assert top["merchant"] == "Amazon" and top["amount_paise"] == 54_999_00


# ------------------------------------------------------------------ evaluation

def test_confusion_and_zero_denominators():
    c = confusion(pd.Series([1, 1, 0, 0, 0]), pd.Series([1, 0, 1, 0, 0]))
    assert (c.tp, c.fn, c.fp, c.tn) == (1, 1, 1, 2)
    assert c.precision == 0.5 and c.recall == 0.5 and c.f1 == 0.5
    assert Confusion(0, 0, 5, 0).precision is None          # nothing flagged
    assert Confusion(0, 0, 5, 0).recall is None             # no anomalies
    assert Confusion(0, 0, 5, 0).f1 is None
    assert Confusion(0, 3, 5, 2).f1 == 0.0                  # P = R = 0


def test_dataset_is_reproducible_and_labelled():
    a, b = anomaly_eval.generate(7), anomaly_eval.generate(7)
    pd.testing.assert_frame_equal(a, b)
    assert not a.equals(anomaly_eval.generate(8))
    kinds = set(a["label_kind"])
    assert {"inflated", "moderate", "new_merchant", "early", "small_unusual", "legit_large", "refund",
            "transfer", "repeated_fixed", "repeated_same_day", "ordinary"} <= kinds
    assert set(a[a.label == 1]["label_kind"]) == {"inflated", "moderate", "new_merchant", "early", "small_unusual"}
    assert (a[a.label_kind.isin(["refund", "transfer", "income"])]["label"] == 0).all()


def test_split_is_temporal():
    r = anomaly_eval.run(anomaly_eval.generate(42), "robust_z_prior", anomaly_eval.TEST)
    assert r["period"] == anomaly_eval.TEST and r["non_expense_flagged"] == 0
    assert r["tp"] + r["fp"] + r["tn"] + r["fn"] == r["eligible"]


def test_committed_results_match_a_fresh_run():
    """docs/anomaly_evaluation.json must be exactly what the code produces (no hand-edited numbers)."""
    committed = json.loads((config.PROJECT_ROOT / "docs" / "anomaly_evaluation.json").read_text(encoding="utf-8"))
    fresh = json.loads(json.dumps(anomaly_eval.evaluate()))
    assert committed == fresh
    default = next(r for r in fresh["results"] if r["method"] == config.ANOMALY.method)
    legacy = next(r for r in fresh["results"] if r["method"] == "iqr_full")
    assert default["test_default"]["f1"] >= legacy["test_default"]["f1"]
    assert default["test_default"]["by_kind"]["small_unusual"]["flagged"] == 0   # documented blind spot


def test_api_evaluation_endpoint():
    from fastapi.testclient import TestClient

    from api import main
    with TestClient(main.app) as c:
        j = c.get("/api/anomalies/evaluation").json()
    assert j["test_period"] == list(anomaly_eval.TEST) and len(j["results"]) == 4
