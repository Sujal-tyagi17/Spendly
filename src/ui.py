"""Shared Streamlit helpers: data mode, connections, sidebar filters, styling."""

from __future__ import annotations

import html
import sqlite3
from datetime import date

import streamlit as st

from src import analytics, config, database, pipeline
from src.analytics import Filters
from src.database import DatabaseError
from src.money import format_inr

MODE_LABELS = {"demo": "Demo data", "user": "My data"}

CSS = """
<style>
:root { --sp-ink:#0b0b0b; --sp-ink2:#52514e; --sp-ink3:#8a8983; --sp-line:#ebeae6;
        --sp-card:#ffffff; --sp-brand:#0f766e; --sp-brand-soft:#e6f2f0; }
.block-container { padding-top: 2.2rem; max-width: 1240px; }
h1, h2, h3 { letter-spacing: -0.01em; }
.sp-hero { display:flex; align-items:baseline; gap:.75rem; margin-bottom:.15rem; }
.sp-hero h1 { margin:0; font-size:1.9rem; font-weight:700; color:var(--sp-ink); }
.sp-sub { color:var(--sp-ink2); margin:0 0 1.1rem 0; font-size:.98rem; }
.sp-badge { display:inline-block; padding:.18rem .6rem; border-radius:999px; font-size:.75rem;
            font-weight:600; letter-spacing:.02em; }
.sp-badge.demo { background:#fff4e0; color:#8a5300; border:1px solid #f3d8a7; }
.sp-badge.user { background:var(--sp-brand-soft); color:var(--sp-brand); border:1px solid #bfdcd7; }
.sp-card { background:var(--sp-card); border:1px solid var(--sp-line); border-radius:14px;
           padding:1rem 1.1rem .9rem; height:100%; box-shadow:0 1px 2px rgba(16,24,40,.04); }
.sp-card .label { color:var(--sp-ink2); font-size:.8rem; font-weight:600; text-transform:uppercase;
                  letter-spacing:.04em; }
.sp-card .value { color:var(--sp-ink); font-size:1.6rem; font-weight:700; margin:.2rem 0 .1rem;
                  font-variant-numeric: tabular-nums; }
.sp-card .note { color:var(--sp-ink3); font-size:.8rem; }
.sp-card .delta-up { color:#b42318; font-weight:600; }
.sp-card .delta-down { color:#067647; font-weight:600; }
.sp-insight { border-left:3px solid var(--sp-line); padding:.45rem .8rem; margin:.35rem 0;
              background:#fff; border-radius:0 10px 10px 0; }
.sp-insight .t { font-weight:600; color:var(--sp-ink); font-size:.88rem; }
.sp-insight .b { color:var(--sp-ink2); font-size:.9rem; }
.sp-insight.up { border-left-color:#e34948; } .sp-insight.down { border-left-color:#2a78d6; }
.sp-insight.warning { border-left-color:#fab219; } .sp-insight.good { border-left-color:#0ca30c; }
.sp-empty { border:1px dashed #d6d4cd; border-radius:14px; padding:1.6rem; text-align:center;
            color:var(--sp-ink2); background:#fcfcfb; }
.sp-empty b { color:var(--sp-ink); }
.sp-chart { background:#fff; border:1px solid var(--sp-line); border-radius:14px; padding:.6rem .8rem .2rem; }
div[data-testid="stSidebar"] .sp-brandline { font-weight:700; font-size:1.25rem; color:var(--sp-ink); }
div[data-testid="stSidebar"] .sp-tag { color:var(--sp-ink2); font-size:.85rem; margin-top:-.2rem; }
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


# ------------------------------------------------------------- data access

def current_mode() -> str:
    if "mode" not in st.session_state:
        # Restore from the URL so a browser refresh keeps the chosen data source.
        st.session_state["mode"] = "user" if st.query_params.get("mode") == "user" else "demo"
    return st.session_state["mode"]


def is_public() -> bool:
    if config.PUBLIC_DEPLOYMENT:
        return True
    try:
        return str(st.secrets.get("SPENDLY_PUBLIC_DEPLOYMENT", "")).lower() in {"1", "true", "yes"}
    except Exception:  # no secrets file locally
        return False


def _prepare(conn: sqlite3.Connection, mode: str) -> sqlite3.Connection:
    if mode == "demo" and database.count_transactions(conn) == 0:
        pipeline.load_demo_dataset(conn)
    return conn


@st.cache_resource(show_spinner=False)
def _file_connection(mode: str) -> sqlite3.Connection:
    """Local use: one SQLite file per mode, kept between runs."""
    return _prepare(database.connect_mode(mode), mode)


def get_conn() -> sqlite3.Connection:
    mode = current_mode()
    try:
        if is_public():
            # Hosted: a private in-memory database per visitor session.
            key = f"_conn_{mode}"
            if key not in st.session_state:
                st.session_state[key] = _prepare(database.connect(":memory:"), mode)
            return st.session_state[key]
        return _file_connection(mode)
    except DatabaseError as exc:
        st.error(str(exc))
        st.stop()


# ----------------------------------------------------------------- filters

def _reset_filters() -> None:
    for key in ("f_dates", "f_categories", "f_types", "f_merchants"):
        st.session_state.pop(key, None)


def sidebar(conn: sqlite3.Connection) -> None:
    with st.sidebar:
        st.markdown(f"<div class='sp-brandline'>₹ {config.APP_NAME}</div>"
                    f"<div class='sp-tag'>{config.TAGLINE}</div>", unsafe_allow_html=True)
        st.write("")
        mode = st.radio("Data source", list(MODE_LABELS), format_func=MODE_LABELS.get,
                        index=list(MODE_LABELS).index(current_mode()), horizontal=True,
                        help="Demo data is synthetic. Your uploads live in a separate database, "
                             "so the two are never mixed.")
        if mode != current_mode():
            st.session_state["mode"] = mode
            _reset_filters()
            st.query_params["mode"] = mode
            st.rerun()
        if st.query_params.get("mode") != mode:
            st.query_params["mode"] = mode

        lo, hi = analytics.date_bounds(conn)
        st.markdown("##### Filters")
        if lo is None:
            st.caption("Filters appear once there is data.")
            return
        st.date_input("Date range", value=(lo, hi), min_value=lo, max_value=hi, key="f_dates",
                      format="DD/MM/YYYY")
        st.multiselect("Category", config.CATEGORIES, key="f_categories", placeholder="All categories")
        st.multiselect("Transaction type", list(config.TRANSACTION_TYPES), key="f_types",
                       format_func=config.TRANSACTION_TYPES.get, placeholder="All types")
        st.multiselect("Merchant", analytics.distinct_values(conn, "normalized_merchant"), key="f_merchants",
                       placeholder="All merchants")
        st.button("Reset filters", on_click=_reset_filters, use_container_width=True)


def current_filters(search: str = "") -> Filters:
    dates = st.session_state.get("f_dates")
    start = end = None
    if isinstance(dates, (tuple, list)):
        if len(dates) >= 1:
            start = dates[0]
        if len(dates) == 2:
            end = dates[1]
    elif isinstance(dates, date):
        start = dates
    return Filters(
        start_date=start, end_date=end,
        categories=tuple(st.session_state.get("f_categories") or ()),
        transaction_types=tuple(st.session_state.get("f_types") or ()),
        merchants=tuple(st.session_state.get("f_merchants") or ()),
        search=search,
    )


def filters_active(filters: Filters, conn) -> bool:
    lo, hi = analytics.date_bounds(conn)
    return bool(filters.categories or filters.transaction_types or filters.merchants
                or (filters.start_date and filters.start_date != lo)
                or (filters.end_date and filters.end_date != hi))


# --------------------------------------------------------------- components

def page_header(title: str, subtitle: str) -> None:
    mode = current_mode()
    badge = ("<span class='sp-badge demo'>DEMO · synthetic data</span>" if mode == "demo"
             else "<span class='sp-badge user'>MY DATA</span>")
    st.markdown(f"<div class='sp-hero'><h1>{html.escape(title)}</h1>{badge}</div>"
                f"<p class='sp-sub'>{html.escape(subtitle)}</p>", unsafe_allow_html=True)


def metric_card(label: str, value: str, note: str = "", delta_html: str = "") -> str:
    return (f"<div class='sp-card'><div class='label'>{html.escape(label)}</div>"
            f"<div class='value'>{html.escape(value)}</div>"
            f"<div class='note'>{delta_html}{html.escape(note)}</div></div>")


def cards(items: list[str]) -> None:
    cols = st.columns(len(items))
    for col, item in zip(cols, items):
        col.markdown(item, unsafe_allow_html=True)


def insight_block(title: str, text: str, tone: str = "neutral") -> None:
    st.markdown(f"<div class='sp-insight {tone}'><div class='t'>{html.escape(title)}</div>"
                f"<div class='b'>{html.escape(text)}</div></div>", unsafe_allow_html=True)


def empty_state(title: str, message: str) -> None:
    st.markdown(f"<div class='sp-empty'><b>{html.escape(title)}</b><br>{html.escape(message)}</div>",
                unsafe_allow_html=True)


def chart(fig, empty_title: str = "Nothing to chart", empty_message: str = "No data matches the current filters.") -> None:
    if fig is None:
        empty_state(empty_title, empty_message)
        return
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def require_data(conn) -> bool:
    """Show an empty state and return False when there are no transactions."""
    if database.count_transactions(conn):
        return True
    if current_mode() == "user":
        empty_state("No statements imported yet",
                    "Go to Import to upload a statement PDF, or switch to Demo data in the sidebar.")
    else:
        empty_state("Demo data is empty", "Use 'Reset demo data' on the Import page to reload it.")
    return False


def safe_query(fn, *args, **kwargs):
    """Run an analytics call, turning filter errors into a friendly message."""
    try:
        return fn(*args, **kwargs)
    except analytics.FilterError as exc:
        st.warning(f"{exc} Adjust the date range in the sidebar.")
        st.stop()


def coverage_note(conn) -> str:
    start, end = database.coverage_period(conn)
    if not start:
        return ""
    return (f"Covers only the uploaded statements: {date.fromisoformat(start).strftime('%d %b %Y')} – "
            f"{date.fromisoformat(end).strftime('%d %b %Y')}.")


def inr(paise) -> str:
    return format_inr(paise)
