import pandas as pd
import streamlit as st

from src import analytics, config, database, ui
from src.money import format_inr
from src.subscription_detector import detect_recurring, recurring_monthly_total

conn = ui.get_conn()
ui.page_header("Recurring Payments", "Subscriptions, bills and other payments that repeat on a schedule.")
if not ui.require_data(conn):
    st.stop()

filters = ui.current_filters()
_, data_end = analytics.date_bounds(conn)
candidates = detect_recurring(ui.safe_query(analytics.recurring_candidates, conn, filters,
                                            config.RECURRING.min_occurrences),
                              database.recurring_decisions(conn), as_of=filters.end_date or data_end)

active = [c for c in candidates if c.status in {"confirmed", "high_confidence"} and not c.possibly_stopped]
monthly = recurring_monthly_total(candidates)
ui.cards([
    ui.metric_card("Active recurring payments", str(len(active)), "confirmed + high confidence"),
    ui.metric_card("Estimated monthly cost", format_inr(monthly), "estimate from median amounts"),
    ui.metric_card("Estimated annual cost", format_inr(monthly * 12), "monthly estimate × 12"),
    ui.metric_card("To review", str(sum(c.status == "possible" for c in candidates)), "possible candidates"),
])
st.caption("A merchant is a candidate when it was paid at least 3 times at regular intervals "
           "(weekly / monthly ±5 days / quarterly / yearly) for a similar amount. "
           "High confidence: every gap fits and amounts stay within 10%. Possible: most gaps fit and amounts "
           "within 30%. Costs are projections, not bills.")

if not candidates:
    ui.empty_state("No recurring payments detected",
                   "Recurring detection needs at least three payments to the same merchant.")
    st.stop()

STATUS = {"confirmed": "✅ Confirmed", "high_confidence": "● High confidence", "possible": "◐ Possible",
          "rejected": "✕ Rejected"}

for group, title in (({"confirmed", "high_confidence"}, "Detected"), ({"possible"}, "Possible — please review"),
                     ({"rejected"}, "Rejected")):
    items = [c for c in candidates if c.status in group]
    if not items:
        continue
    st.markdown(f"### {title}")
    for c in items:
        with st.container(border=True):
            left, mid, right = st.columns([4, 2.2, 1.6])
            stopped = "  \n⚠ _No recent payment — may have been cancelled._" if c.possibly_stopped else ""
            left.markdown(f"**{c.merchant}** · {c.kind} · {c.category}  \n"
                          f"<span class='sp-muted' style='font-size:.88rem'>{c.rationale}</span>{stopped}",
                          unsafe_allow_html=True)
            mid.markdown(f"{STATUS[c.status]} · {c.schedule}  \n"
                         f"**{format_inr(c.est_monthly_paise)}/month** (est.)  \n"
                         f"<span class='sp-muted' style='font-size:.85rem'>{c.occurrences} payments · last "
                         f"{c.last_payment} · next ≈ {c.next_expected}</span>", unsafe_allow_html=True)
            if c.status != "confirmed" and right.button("Confirm", key=f"c_{c.merchant}", width="stretch"):
                database.set_recurring_decision(conn, c.merchant, "confirmed")
                st.rerun()
            if c.status != "rejected" and right.button("Not recurring", key=f"r_{c.merchant}",
                                                       width="stretch"):
                database.set_recurring_decision(conn, c.merchant, "rejected")
                st.rerun()
            if c.status in {"confirmed", "rejected"} and right.button("Undo", key=f"u_{c.merchant}",
                                                                       width="stretch"):
                database.set_recurring_decision(conn, c.merchant, None)
                st.rerun()

with st.expander("Table view"):
    st.dataframe(pd.DataFrame([{
        "Merchant": c.merchant, "Status": STATUS[c.status], "Schedule": c.schedule, "Payments": c.occurrences,
        "Median amount": format_inr(c.median_amount_paise), "Est. monthly": format_inr(c.est_monthly_paise),
        "Est. annual": format_inr(c.est_annual_paise), "Last payment": c.last_payment, "Why": c.rationale,
    } for c in candidates]), hide_index=True, width="stretch")
