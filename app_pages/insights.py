import pandas as pd
import streamlit as st

from src import analytics, anomaly_detector, charts, database, insights, ui
from src.money import format_inr

conn = ui.get_conn()
ui.page_header("Spending Insights", "Why your spending changed — explained from your own numbers.")
if not ui.require_data(conn):
    st.stop()

filters = ui.current_filters()
comp = ui.safe_query(insights.compare_periods, conn, filters)

# ---- 1. What changed
st.markdown("### What changed")
if comp is None:
    ui.empty_state("Not enough history to compare",
                   "A comparison needs the previous month to be covered by your statements.")
else:
    headline = insights.describe_change(comp)
    ui.insight_block(headline.title, headline.text, headline.tone)
    if comp.is_partial:
        st.caption(f"The latest month is partial, so it is compared with the same {comp.current[1].day} days "
                   "of the previous month.")
    left, right = st.columns([3, 2], gap="medium")
    with left:
        ui.chart(charts.period_comparison(comp.categories, comp.current_label, comp.previous_label))
    with right:
        ui.chart(charts.change_bars(comp.categories, "category", "Change by category"),
                 "No change", "Category spending was identical in both periods.")

    st.markdown("#### Merchants behind the change")
    merchants = comp.merchants[comp.merchants["change_paise"] != 0]
    if merchants.empty:
        st.caption("No merchant-level changes.")
    else:
        inc = merchants.sort_values("change_paise", ascending=False).head(5)
        dec = merchants.sort_values("change_paise").head(5)
        dec = dec[dec["change_paise"] < 0]
        inc = inc[inc["change_paise"] > 0]

        def table(df):
            return pd.DataFrame({
                "Merchant": df["merchant"],
                comp.previous_label: df["previous_paise"].map(format_inr),
                comp.current_label: df["current_paise"].map(format_inr),
                "Change": df["change_paise"].map(lambda v: ("+" if v > 0 else "−") + format_inr(abs(v))),
            })
        a, b = st.columns(2, gap="medium")
        for column, heading, data in ((a, "Spent more at", inc), (b, "Spent less at", dec)):
            column.markdown(f"**{heading}**")
            if data.empty:
                column.caption("—")
            else:
                column.dataframe(table(data), hide_index=True, width="stretch")

st.divider()

# ---- 2. Patterns
st.markdown("### Patterns")
left, right = st.columns([3, 2], gap="medium")
with left:
    ui.chart(charts.weekday_columns(ui.safe_query(analytics.weekday_spending, conn, filters)))
with right:
    largest = ui.safe_query(analytics.largest_transactions, conn, filters, limit=8)
    st.markdown("#### Largest payments")
    if largest.empty:
        st.caption("No expenses in view.")
    else:
        st.dataframe(pd.DataFrame({
            "Date": largest["transaction_date"], "Merchant": largest["merchant"],
            "Category": largest["category"], "Amount": largest["amount_paise"].map(format_inr),
        }), hide_index=True, width="stretch")

st.divider()

# ---- 3. Unusual payments
st.markdown("### Unusual payments")
st.caption("Flagged when a payment is far above your EARLIER payments at the same merchant (or, if there isn't "
           "enough history, in the same category): robust z-score ≥ 3.5 **and** at least 2× the median. "
           "Unusual ≠ fraudulent — it's a prompt to take a look.")
show_reviewed = st.toggle("Show reviewed alerts")
txns = ui.safe_query(analytics.transactions, conn, filters)
flagged, info = anomaly_detector.detect_for_view(analytics.transactions(conn), txns, database.anomaly_reviews(conn),
                                                 include_reviewed=show_reviewed)
if flagged.empty:
    st.success("Nothing unusual in the current view.")
else:
    for row in flagged.itertuples():
        with st.container(border=True):
            c1, c2, c3 = st.columns([5, 1.1, 1.1])
            status = "" if row.review_status == "new" else f" · _{row.review_status}_"
            c1.markdown(f"**{row.merchant}** · {row.category} · {row.transaction_date}{status}  \n{row.reason}")
            if c2.button("Expected", key=f"exp_{row.id}", help="I know about this payment"):
                database.set_anomaly_review(conn, row.id, "expected")
                st.rerun()
            if c3.button("Dismiss", key=f"dis_{row.id}", help="Hide this alert"):
                database.set_anomaly_review(conn, row.id, "dismissed")
                st.rerun()
if info["skipped_categories"]:
    skipped = ", ".join(f"{c} ({n})" for c, n in info["skipped_categories"].items())
    st.caption(f"Not enough history to check (fewer than 8 payments): {skipped}.")
