from datetime import date, timedelta

from src import analytics, database
from src.subscription_detector import detect_recurring, recurring_monthly_total
from tests.conftest import conn_from_csv, rows_to_csv


def _monthly(merchant_desc, amounts, start=date(2026, 1, 5), jitter=(0, 1, -1, 2, 0, -2)):
    rows = []
    for i, amount in enumerate(amounts):
        d = date(start.year, start.month + i, start.day) + timedelta(days=jitter[i % len(jitter)])
        rows.append((d.isoformat(), f"{merchant_desc} {i}", f"{amount:.2f}", None))
    return rows


def _detect(rows, decisions=None, as_of=None):
    conn = conn_from_csv(rows_to_csv(rows))
    for merchant, decision in (decisions or {}).items():
        database.set_recurring_decision(conn, merchant, decision)
    return detect_recurring(analytics.recurring_candidates(conn), database.recurring_decisions(conn), as_of=as_of)


def test_consistent_monthly_payment_is_high_confidence():
    found = _detect(_monthly("ACH/DR/NETFLIX.COM", [649] * 5))
    assert len(found) == 1
    c = found[0]
    assert (c.merchant, c.status, c.schedule, c.occurrences) == ("Netflix", "high_confidence", "monthly", 5)
    assert c.est_monthly_paise == 649_00 and c.est_annual_paise == 649_00 * 12
    assert "5 payments" in c.rationale


def test_slightly_changing_amounts_are_still_detected():
    found = _detect(_monthly("AIRTEL POSTPAID BILL", [599, 599, 649, 649, 649]))
    assert found and found[0].status == "high_confidence"   # within 10% of median
    found = _detect(_monthly("BESCOM ELECTRICITY", [800, 1000, 1100, 900, 950]))
    assert found and found[0].status == "possible"          # within 30%


def test_irregular_payments_are_not_recurring():
    rows = [(d, "UPI/DR/ZOMATO ORDER", "350.00", None) for d in
            ["2026-01-02", "2026-01-03", "2026-01-19", "2026-02-27", "2026-03-01", "2026-04-20"]]
    assert _detect(rows) == []


def test_insufficient_observations():
    assert _detect(_monthly("ACH/DR/NETFLIX.COM", [649, 649])) == []


def test_weekly_schedule():
    rows = [((date(2026, 1, 3) + timedelta(days=7 * i)).isoformat(), "MILK DELIVERY WEEKLY", "210.00", None)
            for i in range(6)]
    found = _detect(rows)
    assert found and found[0].schedule == "weekly"
    assert found[0].est_monthly_paise == round(210_00 * 52 / 12)


def test_transfers_are_never_reported_as_subscriptions():
    rows = _monthly("IMPS/DR/SELF TRANSFER TO OWN A/C", [5000] * 5)
    assert _detect(rows) == []


def test_user_decisions_override_detector():
    rows = _monthly("ACH/DR/NETFLIX.COM", [649] * 4)
    assert _detect(rows, {"Netflix": "rejected"})[0].status == "rejected"
    irregular = [(d, "GREEN LEAF SALON", "500.00", None) for d in ["2026-01-02", "2026-02-20", "2026-04-01"]]
    assert _detect(irregular) == []
    assert _detect(irregular, {"Green Leaf Salon": "confirmed"})[0].status == "confirmed"


def test_stopped_subscription_is_flagged_and_excluded_from_total():
    found = _detect(_monthly("ACH/DR/NETFLIX.COM", [649] * 3), as_of=date(2026, 8, 1))
    assert found[0].possibly_stopped
    assert recurring_monthly_total(found) == 0


def test_demo_dataset_subscriptions(demo_conn):
    found = detect_recurring(analytics.recurring_candidates(demo_conn))
    merchants = {c.merchant for c in found if c.status == "high_confidence"}
    assert {"Netflix", "Spotify", "Cult.fit", "Airtel", "JioHotstar"} <= merchants
    assert "Zomato" not in merchants and "Own account transfer" not in merchants
