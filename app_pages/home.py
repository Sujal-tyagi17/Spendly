import pandas as pd
import streamlit as st

from src import ai, config, database, pipeline, ui
from src.money import format_inr
from src.pdf_parser import PasswordRequiredError, StatementError, supported_formats

conn = ui.get_conn()
mode = ui.current_mode()
ui.page_header("Import & Settings", "Turn a statement PDF into clean, categorized transactions.")

if ui.is_public():
    st.info("**Hosted demo:** anything you upload is kept only in this browser session's memory and disappears "
            "when you close the tab. For your real statements, run Spendly on your own computer.")

# ------------------------------------------------------------------ demo mode
if mode == "demo":
    st.markdown("### You're viewing the demo")
    st.write("The demo is a **synthetic** six-month statement (April–September 2026) built to show every "
             "feature: salary, refunds, own-account transfers, card bills, subscriptions, a duplicate row, "
             "uncategorized local shops and an unusually large purchase. No real person's data is included.")
    c1, c2 = st.columns([1, 3])
    if c1.button("Reset demo data", help="Rebuild the demo from the sample file (undoes your edits)."):
        pipeline.load_demo_dataset(conn)
        st.success("Demo data reloaded.")
        st.rerun()
    c2.write("To analyse your own statement, switch **Data source → My data** in the sidebar.")

    st.markdown("#### Try the upload flow with synthetic PDFs")
    st.caption("Download one of these, switch to *My data*, and upload it.")
    d1, d2, _ = st.columns([1, 1, 2])
    sample_dir = config.PROJECT_ROOT / "data" / "sample_statements"
    for col, name, label in ((d1, "sample_bank_statement.pdf", "Sample bank statement"),
                             (d2, "sample_phonepe_statement.pdf", "Sample PhonePe statement")):
        path = sample_dir / name
        if path.exists():
            col.download_button(label, path.read_bytes(), file_name=name, mime="application/pdf",
                                width="stretch")
    st.stop()

# ------------------------------------------------------------------ user mode
st.markdown("### Upload a statement")
with st.expander("Supported formats & tips", expanded=False):
    for label in supported_formats():
        st.markdown(f"- {label}")
    st.markdown(
        f"- Text-based PDFs only (downloaded from net-banking or the app). Scanned PDFs need OCR, "
        "which isn't supported yet.\n"
        f"- Maximum {config.UPLOAD.max_file_size_mb} MB / {config.UPLOAD.max_pages} pages.\n"
        "- Password-protected statements are fine — enter the password below; it is used only to open "
        "the file and is never stored.\n"
        "- Always check the preview: every bank prints statements a little differently."
    )

uploaded = st.file_uploader("Statement PDF", type=["pdf"], accept_multiple_files=False,
                            help="Processed in memory. The PDF itself is never saved.")
password = st.text_input("PDF password (if any)", type="password")

if uploaded is not None:
    signature = (uploaded.name, uploaded.size, password)
    if st.session_state.get("preview_sig") != signature:
        st.session_state.pop("preview", None)
        try:
            with st.spinner("Reading statement…"):
                st.session_state["preview"] = pipeline.prepare_pdf_import(uploaded.getvalue(), uploaded.name,
                                                                         conn, password or None)
            st.session_state["preview_sig"] = signature
            st.session_state.pop("preview_error", None)
        except PasswordRequiredError as exc:
            st.session_state["preview_error"] = ("warning", str(exc))
        except StatementError as exc:
            st.session_state["preview_error"] = ("error", str(exc))
        except Exception:  # unexpected: never show a raw stack trace
            st.session_state["preview_error"] = ("error", "Something went wrong while reading this PDF. "
                                                          "Please try another file or report the issue.")
            st.session_state["preview_sig"] = signature
    error = st.session_state.get("preview_error")
    if error and "preview" not in st.session_state:
        if error[0] == "warning":
            st.warning(error[1])
        else:
            st.error(error[1])

preview = st.session_state.get("preview") if uploaded is not None else None
if preview is not None:
    st.markdown("### Preview")
    st.caption(f"Detected format: **{preview.parser_label}** · period "
               f"{preview.period_start} → {preview.period_end}")
    q = preview.quality
    ui.cards([
        ui.metric_card("Rows found", str(q.total_extracted), f"{q.invalid} unreadable"),
        ui.metric_card("Ready to import", str(len(preview.rows) - preview.exact_duplicates),
                       f"{preview.exact_duplicates} exact duplicates will be skipped"),
        ui.metric_card("Possible duplicates", str(preview.possible_duplicates), "imported & flagged for review"),
        ui.metric_card("Uncategorized", str(preview.uncategorized), "you can fix these later"),
    ])
    for warning in preview.warnings:
        st.warning(warning)

    frame = preview.to_frame()
    if not frame.empty:
        status_label = {"none": "", "possible": "possible duplicate", "exact_in_file": "duplicate (skipped)",
                        "exact_existing": "already imported (skipped)"}
        st.dataframe(pd.DataFrame({
            "Date": frame["transaction_date"],
            "Description": frame["description"],
            "Merchant": frame["normalized_merchant"],
            "Amount": [("−" if d == "debit" else "+") + format_inr(a, decimals=True)
                       for d, a in zip(frame["direction"], frame["amount_paise"])],
            "Type": frame["transaction_type"].map(config.TRANSACTION_TYPES),
            "Category": frame["category"],
            "Note": frame["duplicate_status"].map(status_label),
        }), hide_index=True, width="stretch", height=360)
    if preview.invalid_rows:
        with st.expander(f"{len(preview.invalid_rows)} row(s) could not be read"):
            st.dataframe(pd.DataFrame(preview.invalid_rows), hide_index=True, width="stretch")

    # Optional AI categorization
    enabled, status = ai.ai_status()
    uncategorized = sorted({r["normalized_merchant"] for r in preview.rows
                            if r["categorization_method"] == "none" and r["direction"] == "debit"})
    if uncategorized:
        if enabled:
            with st.expander(f"Suggest categories for {len(uncategorized)} merchant(s) with Gemini"):
                st.caption("Only these sanitized merchant labels are sent — no amounts, dates, balances or "
                           "account details:")
                st.code(", ".join(ai.preview_payload(uncategorized)) or "(nothing to send)")
                if st.button("Send to Gemini"):
                    try:
                        changed = pipeline.apply_ai_suggestions(preview, ai.suggest_categories(uncategorized))
                        st.success(f"{changed} row(s) received an AI-suggested category (marked for review).")
                        st.rerun()
                    except ai.AIError as exc:
                        st.warning(str(exc))
        else:
            st.caption(f"Optional AI categorization: {status}")

    include_dups = False
    if preview.exact_duplicates:
        include_dups = st.checkbox("Import exact duplicates anyway (not recommended)")
    if st.button("Import transactions", type="primary", disabled=preview.already_imported or not preview.rows):
        try:
            pipeline.commit_import(conn, preview, include_exact_duplicates=include_dups)
        except Exception:
            st.error("The import failed and nothing was saved. Please try again.")
        else:
            st.session_state.pop("preview", None)
            st.session_state.pop("preview_sig", None)
            st.success("Imported! Open Overview to explore your spending.")
            st.balloons()

# ------------------------------------------------------------------ your data
st.divider()
st.markdown("### Your data")
statements = database.list_statements(conn)
if statements:
    st.dataframe(pd.DataFrame([{
        "Statement": s["display_name"], "Format": s["parser_name"],
        "Period": f"{s['statement_period_start']} → {s['statement_period_end']}",
        "Transactions": s["rows_imported"], "Imported": s["created_at"][:16].replace("T", " "),
    } for s in statements]), hide_index=True, width="stretch")
else:
    st.caption("Nothing imported yet.")

where = "this browser session's memory" if ui.is_public() else f"`{config.db_path('user')}`"
st.markdown(f"Imported transactions are stored in a local, **unencrypted** SQLite database at {where}. "
            "Uploaded PDFs are never saved.")
with st.popover("Delete all my data", disabled=not statements):
    st.write("This permanently deletes every imported statement, transaction, category correction and "
             "review decision from the *My data* database.")
    if st.button("Yes, delete everything", type="primary"):
        database.clear_all_data(conn)
        st.session_state.pop("preview", None)
        st.success("All imported data deleted.")
        st.rerun()
