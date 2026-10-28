"""Spendly — Every rupee tells a story.

Run with:  streamlit run app.py
"""

import streamlit as st

from src import config, ui
from src.privacy import get_logger

get_logger("spendly")

st.set_page_config(page_title=f"{config.APP_NAME} · {config.TAGLINE}", page_icon="assets/logo.svg",
                   layout="wide", initial_sidebar_state="expanded")
ui.inject_css()

pages = [
    st.Page("app_pages/overview.py", title="Overview", icon=":material/space_dashboard:", default=True),
    st.Page("app_pages/transactions.py", title="Transactions", icon=":material/receipt_long:"),
    st.Page("app_pages/insights.py", title="Spending Insights", icon=":material/insights:"),
    st.Page("app_pages/recurring.py", title="Recurring Payments", icon=":material/autorenew:"),
    st.Page("app_pages/data_quality.py", title="Data Quality", icon=":material/fact_check:"),
    st.Page("app_pages/home.py", title="Import & Settings", icon=":material/upload_file:"),
]
navigation = st.navigation(pages)

conn = ui.get_conn()
ui.sidebar(conn)
navigation.run()
