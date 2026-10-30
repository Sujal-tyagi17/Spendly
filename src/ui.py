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
/* Same tokens as the web app (web/app/globals.css). */
:root { --sp-ink:#f5f7f2; --sp-ink2:#929a90; --sp-ink3:#828a80; --sp-line:#1e261e; --sp-line2:#2a342a;
        --sp-card:#111511; --sp-card2:#151b14; --sp-brand:#c6ff5e; --sp-brand-soft:rgba(198,255,94,.10);
        --sp-pos:#7fc98a; --sp-neg:#e06c5f; --sp-warn:#e8b04b; --sp-info:#8fb8de; }
.block-container { padding-top: 2.2rem; max-width: 1240px; }
h1, h2, h3 { letter-spacing: -0.02em; }
.sp-hero { display:flex; align-items:baseline; gap:.75rem; margin-bottom:.15rem; }
.sp-hero h1 { margin:0; font-size:1.9rem; font-weight:600; color:var(--sp-ink); letter-spacing:-0.03em; }
.sp-sub { color:var(--sp-ink2); margin:0 0 1.1rem 0; font-size:.98rem; }
.sp-badge { display:inline-block; padding:.18rem .6rem; border-radius:999px; font-size:.75rem;
            font-weight:600; letter-spacing:.02em; }
.sp-badge.demo { background:rgba(232,176,75,.10); color:var(--sp-warn); border:1px solid rgba(232,176,75,.35); }
.sp-badge.user { background:var(--sp-brand-soft); color:var(--sp-brand); border:1px solid rgba(198,255,94,.35); }
.sp-card { background:var(--sp-card); border:1px solid var(--sp-line); border-radius:16px;
           padding:1rem 1.1rem .9rem; height:100%; }
.sp-card .label { color:var(--sp-ink3); font-size:.7rem; font-weight:500; text-transform:uppercase;
                  letter-spacing:.14em; font-family:"Geist Mono", ui-monospace, monospace; }
.sp-card .value { color:var(--sp-ink); font-size:1.6rem; font-weight:600; margin:.25rem 0 .1rem;
                  font-variant-numeric: tabular-nums; letter-spacing:-0.02em; }
.sp-card .note { color:var(--sp-ink2); font-size:.8rem; }
.sp-card .delta-up { color:var(--sp-neg); font-weight:600; }
.sp-card .delta-down { color:var(--sp-pos); font-weight:600; }
.sp-insight { border-left:3px solid var(--sp-line2); padding:.5rem .85rem; margin:.4rem 0;
              background:var(--sp-card); border-radius:0 12px 12px 0; }
.sp-insight .t { font-weight:600; color:var(--sp-ink); font-size:.88rem; }
.sp-insight .b { color:var(--sp-ink2); font-size:.9rem; }
.sp-insight.up { border-left-color:var(--sp-neg); } .sp-insight.down { border-left-color:var(--sp-pos); }
.sp-insight.warning { border-left-color:var(--sp-warn); } .sp-insight.good { border-left-color:var(--sp-brand); }
.sp-empty { border:1px dashed var(--sp-line2); border-radius:16px; padding:1.6rem; text-align:center;
            color:var(--sp-ink2); background:var(--sp-card); }
.sp-empty b { color:var(--sp-ink); }
.sp-chart { background:var(--sp-card); border:1px solid var(--sp-line); border-radius:16px; padding:.6rem .8rem .2rem; }
.sp-muted { color:var(--sp-ink2); }
div[data-testid="stSidebar"] .sp-brandline { display:flex; align-items:center; gap:0.6rem; font-weight:600; font-size:1.2rem; color:var(--sp-ink); }
div[data-testid="stSidebar"] .sp-tag { color:var(--sp-ink2); font-size:.85rem; margin-top:.35rem; line-height:1.4; }
/* Primary buttons: lime with dark text, like the web app. */
button[data-testid="stBaseButton-primary"] { color:#080a08 !important; font-weight:600; }
button[data-testid="stBaseButton-primary"] * { color:#080a08 !important; }
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

_FILTER_KEYS = ("f_dates", "f_categories", "f_types", "f_merchants")


def _fk(name: str) -> str:
    """Widget key for a filter, per data source. Streamlit remembers a widget by its key, so a
    shared key let the demo's date range follow you into My data (and vice versa)."""
    return f"{name}_{current_mode()}"


def _reset_filters() -> None:
    for key in _FILTER_KEYS:
        st.session_state.pop(_fk(key), None)


# The same mark as the web app (web/components/logo.tsx), inline so it needs no extra request.
_LOGO_MARK = (
    "<svg viewBox='0 0 32 32' width='28' height='28' aria-hidden='true'>"
    "<rect width='32' height='32' rx='9' fill='#111511' stroke='#2a342a'/>"
    "<rect x='8' y='17' width='4' height='7' rx='1.5' fill='#c6ff5e' opacity='0.45'/>"
    "<rect x='14' y='12' width='4' height='12' rx='1.5' fill='#c6ff5e' opacity='0.7'/>"
    "<rect x='20' y='7' width='4' height='17' rx='1.5' fill='#c6ff5e'/></svg>"
)


def sidebar(conn: sqlite3.Connection) -> None:
    with st.sidebar:
        st.markdown(f"<div class='sp-brandline' style='display:flex;align-items:center;gap:0.6rem'>{_LOGO_MARK}<span style='font-weight:700'>{config.APP_NAME}</span></div>"
                    f"<div class='sp-tag' style='color:#929a90;font-size:.85rem;line-height:1.45;margin-top:.4rem'>{config.TAGLINE}</div>", unsafe_allow_html=True)
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
        st.session_state["f_bounds"] = (lo, hi)
        st.date_input("Date range", value=(lo, hi), min_value=lo, max_value=hi, key=_fk("f_dates"),
                      format="DD/MM/YYYY")
        st.multiselect("Category", config.CATEGORIES, key=_fk("f_categories"), placeholder="All categories")
        st.multiselect("Transaction type", list(config.TRANSACTION_TYPES), key=_fk("f_types"),
                       format_func=config.TRANSACTION_TYPES.get, placeholder="All types")
        st.multiselect("Merchant", analytics.distinct_values(conn, "normalized_merchant"), key=_fk("f_merchants"),
                       placeholder="All merchants")
        st.button("Reset filters", on_click=_reset_filters, width="stretch")


def current_filters(search: str = "") -> Filters:
    dates = st.session_state.get(_fk("f_dates"))
    start = end = None
    if isinstance(dates, (tuple, list)):
        if len(dates) >= 1:
            start = dates[0]
        if len(dates) == 2:
            end = dates[1]
    elif isinstance(dates, date):
        start = dates
    # The untouched range (first to last transaction) means "all dates", exactly like the web
    # app with no date filter. Passing it on would end the analysis at the last transaction
    # (e.g. 16 Dec) and turn a full statement month into a "partial month" comparison.
    if (start, end) == st.session_state.get("f_bounds"):
        start = end = None
    return Filters(
        start_date=start, end_date=end,
        categories=tuple(st.session_state.get(_fk("f_categories")) or ()),
        transaction_types=tuple(st.session_state.get(_fk("f_types")) or ()),
        merchants=tuple(st.session_state.get(_fk("f_merchants")) or ()),
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
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


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
