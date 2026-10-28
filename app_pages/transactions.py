import pandas as pd
import streamlit as st

from src import analytics, config, database, ui
from src.categorizer import type_for_manual_category
from src.money import format_inr

conn = ui.get_conn()
ui.page_header("Transactions", "Search, review and correct every transaction. Changes update all charts.")
if not ui.require_data(conn):
    st.stop()

TYPE_LABELS = config.TRANSACTION_TYPES
LABEL_TO_TYPE = {v: k for k, v in TYPE_LABELS.items()}
METHOD_LABELS = {"rule": "Rule", "merchant": "Merchant rule", "ai": "AI suggestion", "manual": "Manual",
                 "none": "Uncategorized"}

top = st.columns([3, 1.2, 1.2, 1])
search = top[0].text_input("Search", placeholder="Search merchant or description…", label_visibility="collapsed")
review_only = top[1].toggle("Needs review only")
page_size = top[2].selectbox("Rows per page", [25, 50, 100, 250], index=1, label_visibility="collapsed")

filters = ui.current_filters(search)
frame = ui.safe_query(analytics.transactions, conn, filters)
if review_only:
    frame = frame[frame["review_status"] == "needs_review"]

if frame.empty:
    ui.empty_state("No matching transactions", "Try a different search or clear the filters in the sidebar.")
    st.stop()

# ---- summary strip
debits = frame.loc[frame["direction"] == "debit", "amount_paise"].sum()
credits = frame.loc[frame["direction"] == "credit", "amount_paise"].sum()
st.caption(f"{len(frame):,} transactions · debits {format_inr(debits)} · credits {format_inr(credits)} · "
           f"{int((frame['review_status'] == 'needs_review').sum())} need review")

# ---- pagination
pages = max(1, -(-len(frame) // page_size))
page = top[3].number_input("Page", min_value=1, max_value=pages, value=1, step=1,
                           label_visibility="collapsed", help=f"{pages} page(s)") if pages > 1 else 1
chunk = frame.iloc[(page - 1) * page_size: page * page_size]

view = pd.DataFrame({
    "id": chunk["id"].astype(int),
    "Date": pd.to_datetime(chunk["transaction_date"]).dt.date,
    "Merchant": chunk["normalized_merchant"],
    "Amount (₹)": (chunk["amount_paise"] / 100) * chunk["direction"].map({"debit": -1, "credit": 1}),
    "Type": chunk["transaction_type"].map(TYPE_LABELS),
    "Category": chunk["category"],
    "Method": chunk["categorization_method"].map(METHOD_LABELS),
    "Status": chunk.apply(lambda r: ("⚠ possible duplicate" if r["is_possible_duplicate"] else
                                     "needs review" if r["review_status"] == "needs_review" else
                                     "reviewed" if r["review_status"] == "reviewed" else "ok"), axis=1),
    "Mark reviewed": False,
    "Delete": False,
    "Description": chunk["description"],
}).set_index("id")

edited = st.data_editor(
    view,
    key=f"editor_{page}_{hash(filters)}_{review_only}_{page_size}",
    width="stretch",
    height=min(38 * (len(view) + 1) + 4, 640),
    disabled=["Date", "Merchant", "Amount (₹)", "Method", "Status", "Description"],
    column_config={
        "Amount (₹)": st.column_config.NumberColumn(format="%.2f", help="Negative = money out"),
        "Type": st.column_config.SelectboxColumn(options=list(TYPE_LABELS.values()), required=True),
        "Category": st.column_config.SelectboxColumn(options=config.CATEGORIES, required=True),
        "Mark reviewed": st.column_config.CheckboxColumn(help="Confirms the row is correct (also clears a duplicate flag)"),
        "Delete": st.column_config.CheckboxColumn(help="Remove a real duplicate"),
        "Description": st.column_config.TextColumn(width="large", help="Original statement text (identifiers masked)"),
    },
)

changed_rows = []
for txn_id, new in edited.iterrows():
    old = view.loc[txn_id]
    if (new["Type"] != old["Type"] or new["Category"] != old["Category"] or new["Mark reviewed"] or new["Delete"]):
        changed_rows.append((int(txn_id), old, new))

c1, c2, c3 = st.columns([1.2, 2.2, 2])
apply_merchant = c2.checkbox("Apply category changes to every transaction from the same merchant",
                             help="Useful for local shops: fix one row, fix them all.")
confirm_delete = any(new["Delete"] for _, _, new in changed_rows)
if confirm_delete:
    sure = c3.checkbox("Yes, permanently delete the ticked rows")
else:
    sure = False

if c1.button(f"Save {len(changed_rows)} change(s)" if changed_rows else "No changes", type="primary",
             disabled=not changed_rows):
    if confirm_delete and not sure:
        st.warning("Tick the confirmation box to delete rows.")
        st.stop()
    applied = 0
    for txn_id, old, new in changed_rows:
        record = database.get_transaction(conn, txn_id)
        if record is None:
            continue
        if new["Delete"]:
            database.delete_transaction(conn, txn_id)
            applied += 1
            continue
        changes = {}
        new_type = LABEL_TO_TYPE[new["Type"]]
        if new["Category"] != old["Category"]:
            changes["category"] = new["Category"]
            if new["Type"] == old["Type"]:
                new_type = type_for_manual_category(new["Category"], record["direction"], record["transaction_type"])
        if new_type != record["transaction_type"]:
            changes["transaction_type"] = new_type
        if new["Mark reviewed"]:
            changes["review_status"] = "reviewed"
            changes["is_possible_duplicate"] = 0
        targets = [txn_id]
        if apply_merchant and "category" in changes:
            targets = [r[0] for r in conn.execute(
                "SELECT id FROM transactions WHERE normalized_merchant = ? AND direction = ?",
                (record["normalized_merchant"], record["direction"]))]
        for target in targets:
            database.update_transaction_fields(conn, target, changes)
            applied += 1
    st.success(f"Saved {applied} update(s).")
    st.rerun()

# ---- export
export = frame.assign(
    amount_inr=(frame["amount_paise"] / 100).round(2),
    balance_inr=(frame["balance_paise"] / 100).round(2),
)[["transaction_date", "normalized_merchant", "description", "direction", "amount_inr", "transaction_type",
   "category", "categorization_method", "review_status", "balance_inr"]]
st.download_button("Download these transactions (CSV)", export.to_csv(index=False).encode("utf-8"),
                   file_name="spendly_transactions.csv", mime="text/csv",
                   help="Exports every row matching the current search and filters.")
