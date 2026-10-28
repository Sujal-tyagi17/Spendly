import streamlit as st

from src import ai, analytics, charts, insights, subscription_detector, anomaly_detector, database, ui
from src.money import format_inr

conn = ui.get_conn()
ui.page_header("Overview", "Where your money went, and what changed.")
if not ui.require_data(conn):
    st.stop()

filters = ui.current_filters()
totals = ui.safe_query(analytics.totals, conn, filters)
monthly = ui.safe_query(analytics.monthly_summary, conn, filters)

if not totals["transaction_count"]:
    ui.empty_state("No transactions match these filters", "Widen the date range or clear filters in the sidebar.")
    st.stop()

# ---- KPI cards
comparison = insights.compare_periods(conn, filters)
if comparison is None:
    mom_value, mom_note, delta = "—", "needs two months of data", ""
elif comparison.change_pct is None:
    mom_value, mom_note, delta = "New", f"no spending in {comparison.previous_label}", ""
else:
    pct = comparison.change_pct
    css = "delta-up" if pct > 0 else "delta-down"
    arrow = "▲" if pct > 0 else "▼" if pct < 0 else "■"
    mom_value = f"{pct:+.1f}%"
    delta = f"<span class='{css}'>{arrow}</span> "
    mom_note = f"{comparison.current_label} vs {comparison.previous_label}"

ui.cards([
    ui.metric_card("Expenditure", format_inr(totals["expenditure_paise"]),
                   f"net of refunds: {format_inr(totals['expenditure_paise'] - totals['refunds_paise'])}"),
    ui.metric_card("Income received", format_inr(totals["income_paise"]),
                   "salary, interest & other recognised income"),
    ui.metric_card("Net cash flow", format_inr(totals["net_cash_flow_paise"]),
                   "all credits − all debits, excl. own-account transfers"),
    ui.metric_card("Month-over-month", mom_value, mom_note, delta),
])

with st.expander("How are these numbers defined?"):
    st.markdown(
        """
- **Expenditure** — debits classified as spending. Internal transfers between your own accounts and
  credit-card bill payments are *excluded* (the card purchases themselves are the spending).
- **Net expenditure** — expenditure minus refunds.
- **Income received** — credits recognised as income (salary, stipend, interest). Money from friends
  is *not* counted as income; it stays "Other" until you re-categorize it.
- **Net cash flow** — every credit minus every debit, excluding internal transfers. Credit-card bill
  payments *are* included here because the money really left your account.
- **Month-over-month** — change in expenditure for the latest month in view vs the previous month.
  A partial month is compared with the same number of days of the previous month.
        """
    )
note = ui.coverage_note(conn)
if note:
    st.caption(note + (" Filters are active." if ui.filters_active(filters, conn) else ""))

# ---- charts
left, right = st.columns([3, 2], gap="medium")
with left:
    ui.chart(charts.monthly_trend(monthly))
with right:
    ui.chart(charts.category_bars(ui.safe_query(analytics.category_spending, conn, filters)))

left, right = st.columns([2, 3], gap="medium")
with left:
    ui.chart(charts.merchant_bars(ui.safe_query(analytics.top_merchants, conn, filters, limit=5)))
with right:
    st.markdown("#### Key insights")
    recurring = subscription_detector.detect_recurring(
        analytics.recurring_candidates(conn, filters), database.recurring_decisions(conn))
    anomalies, _ = anomaly_detector.detect_for_view(analytics.transactions(conn), analytics.transactions(conn, filters),
                                                    database.anomaly_reviews(conn))
    items = insights.build_insights(conn, filters, recurring, anomalies)
    for item in items:
        ui.insight_block(item.title, item.text, item.tone)

    enabled, status = ai.ai_status()
    if enabled and items:
        if st.button("Summarise with Gemini", help="Sends only the insight sentences above — no transactions."):
            try:
                summary = ai.rephrase_insights([i.text for i in items])
            except ai.AIError as exc:
                st.warning(str(exc))
            else:
                if summary:
                    st.info(f"✨ AI summary (checked against the numbers above): {summary}")
                else:
                    st.caption("The AI summary didn't match the computed numbers, so it was discarded.")
