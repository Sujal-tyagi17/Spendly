import pandas as pd

from src import analytics, database
from src.anomaly_detector import detect_anomalies


def frame(amounts_by_category: dict[str, list[int]], merchant_for=lambda cat, i: f"{cat} shop {i}"):
    rows, next_id = [], 1
    for category, amounts in amounts_by_category.items():
        for i, amount in enumerate(amounts):
            rows.append({"id": next_id, "transaction_date": f"2026-01-{(i % 28) + 1:02d}",
                         "normalized_merchant": merchant_for(category, i), "category": category,
                         "amount_paise": amount * 100, "direction": "debit", "transaction_type": "expense"})
            next_id += 1
    return pd.DataFrame(rows)


def test_typical_transactions_are_not_flagged():
    flagged, _ = detect_anomalies(frame({"Food & Dining": [300, 320, 280, 350, 310, 290, 330, 300, 340, 310]}))
    assert flagged.empty


def test_large_outlier_is_flagged_with_explanation():
    flagged, _ = detect_anomalies(frame({"Food & Dining": [300, 320, 280, 350, 310, 290, 330, 300, 340, 2800]}))
    assert len(flagged) == 1
    row = flagged.iloc[0]
    assert row["amount_paise"] == 2800_00 and row["basis"] == "category"
    assert "your usual Food & Dining spending" in row["reason"] and "×" in row["reason"]
    assert "fraud" not in row["reason"].lower()


def test_small_datasets_are_skipped_not_guessed():
    flagged, info = detect_anomalies(frame({"Travel": [500, 600, 50_000]}))
    assert flagged.empty
    assert info["skipped_categories"] == {"Travel": 3}


def test_comparison_is_category_specific():
    # ₹1,800 is normal for Groceries but would be huge for Transport.
    data = frame({"Groceries": [1500, 1700, 1800, 1600, 1750, 1650, 1550, 1800],
                  "Transport": [60, 80, 70, 90, 65, 75, 85, 1800]})
    flagged, _ = detect_anomalies(data)
    assert list(flagged["category"]) == ["Transport"]


def test_merchant_history_is_preferred_when_available():
    # Rent is always ₹18,000 — compared with its own history it is normal even
    # though it dwarfs the rest of the category.
    data = frame({"Other": [100, 120, 90, 110, 130, 95, 105, 115, 18000, 18000, 18000, 18000, 18000]},
                 merchant_for=lambda cat, i: "Landlord" if i >= 8 else f"Shop {i}")
    flagged, _ = detect_anomalies(data)
    assert flagged.empty


def test_tight_spread_does_not_flag_tiny_differences():
    flagged, _ = detect_anomalies(frame({"Transport": [40, 40, 40, 40, 40, 40, 40, 40, 60]}))
    assert flagged.empty  # 60 is above Q3+1.5*IQR (=40) but not 2x the median


def test_dismissed_alerts_do_not_return(demo_conn):
    txns = analytics.transactions(demo_conn)
    flagged, _ = detect_anomalies(txns, database.anomaly_reviews(demo_conn))
    assert not flagged.empty
    first = int(flagged.iloc[0]["id"])
    database.set_anomaly_review(demo_conn, first, "dismissed")
    again, _ = detect_anomalies(txns, database.anomaly_reviews(demo_conn))
    assert first not in set(again["id"])
    with_reviewed, _ = detect_anomalies(txns, database.anomaly_reviews(demo_conn), include_reviewed=True)
    assert first in set(with_reviewed["id"])


def test_demo_laptop_purchase_is_flagged(demo_conn):
    flagged, _ = detect_anomalies(analytics.transactions(demo_conn))
    top = flagged.iloc[0]
    assert top["merchant"] == "Amazon" and top["amount_paise"] == 54_999_00


def test_empty_input():
    flagged, info = detect_anomalies(pd.DataFrame())
    assert flagged.empty and info["checked_categories"] == []
