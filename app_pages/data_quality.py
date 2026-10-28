import pandas as pd
import streamlit as st

from src import analytics, database, ui
from src.money import format_inr

conn = ui.get_conn()
ui.page_header("Data Quality", "How much you can trust the numbers — extraction, duplicates and gaps.")
if not ui.require_data(conn):
    st.stop()

statements = database.list_statements(conn)
extracted = sum(s["rows_extracted"] for s in statements)
invalid = sum(s["rows_invalid"] for s in statements)
skipped = sum(s["rows_skipped_duplicates"] for s in statements)
checked = sum(s["balance_checked_pairs"] for s in statements)
mismatch = sum(s["balance_mismatches"] for s in statements)
totals = analytics.totals(conn)  # whole dataset, not filtered: quality is about the data itself
corrections = conn.execute("SELECT COUNT(*) FROM manual_corrections").fetchone()[0]

rate = f"{100 * (extracted - invalid) / extracted:.1f}%" if extracted else "—"
balance = f"{100 * (checked - mismatch) / checked:.1f}%" if checked else "n/a"
ui.cards([
    ui.metric_card("Rows read successfully", rate, f"{extracted - invalid:,} of {extracted:,} extracted"),
    ui.metric_card("Running balance check", balance,
                   f"{mismatch} mismatch(es) in {checked:,} pairs" if checked else "no balance column"),
    ui.metric_card("Duplicates", f"{skipped} skipped",
                   f"{int(totals['possible_duplicate_count'] or 0)} possible, awaiting review"),
    ui.metric_card("Uncategorized", str(int(totals["uncategorized_count"])),
                   f"{int(totals['needs_review_count'])} rows need review · {corrections} manual fixes"),
])
st.caption("**Rows read successfully** = rows with a valid date, description and amount ÷ rows extracted. "
           "**Running balance check** = share of consecutive rows where previous balance ± amount equals the "
           "printed balance — a mismatch usually means a missing or mis-read row.")

st.markdown("### Imported statements")
st.dataframe(pd.DataFrame([{
    "Statement": s["display_name"], "Format": s["parser_name"],
    "Period": f"{s['statement_period_start']} → {s['statement_period_end']}",
    "Extracted": s["rows_extracted"], "Imported": s["rows_imported"], "Invalid": s["rows_invalid"],
    "Duplicates skipped": s["rows_skipped_duplicates"],
    "Balance mismatches": f"{s['balance_mismatches']}/{s['balance_checked_pairs']}" if s["balance_checked_pairs"] else "n/a",
    "Imported on": s["created_at"][:10],
} for s in statements]), hide_index=True, width="stretch")

warnings = [(s["display_name"], w) for s in statements for w in s["warnings"]]
if warnings:
    st.markdown("### Processing warnings")
    for name, warning in warnings:
        st.warning(f"**{name}:** {warning}")

issues = pd.read_sql_query(
    """SELECT s.display_name AS statement, i.page, i.row_number, i.reason
       FROM import_issues i JOIN statements s ON s.id = i.statement_id ORDER BY i.statement_id, i.row_number""",
    conn)
st.markdown("### Rows that could not be imported")
if issues.empty:
    st.success("Every extracted row was readable.")
else:
    st.dataframe(issues, hide_index=True, width="stretch")

left, right = st.columns(2, gap="medium")
with left:
    st.markdown("### Possible duplicates")
    dups = pd.read_sql_query(
        """SELECT transaction_date AS date, normalized_merchant AS merchant, amount_paise, description
           FROM transactions WHERE is_possible_duplicate = 1 ORDER BY transaction_date""", conn)
    if dups.empty:
        st.success("None waiting for review.")
    else:
        dups["amount"] = dups.pop("amount_paise").map(format_inr)
        st.dataframe(dups, hide_index=True, width="stretch")
        st.caption("Same date, amount and merchant as another row. Identical payments can be genuine (two coffees), "
                   "so nothing is deleted automatically — resolve them on the Transactions page.")
with right:
    st.markdown("### Uncategorized merchants")
    unc = analytics.uncategorized(conn)
    if unc.empty:
        st.success("Everything is categorized.")
    else:
        st.dataframe(pd.DataFrame({
            "Merchant": unc["merchant"], "Direction": unc["direction"], "Rows": unc["transaction_count"],
            "Total": unc["total_paise"].map(format_inr),
        }), hide_index=True, width="stretch")
        st.caption("Tip: on Transactions, change one row and tick “apply to every transaction from the same merchant”.")

missing = conn.execute(
    """SELECT SUM(balance_paise IS NULL), SUM(normalized_merchant = 'Unknown'), COUNT(*) FROM transactions""").fetchone()
st.markdown("### Missing fields")
st.write(f"- Rows without a running balance: **{missing[0] or 0}** of {missing[2]}  \n"
         f"- Rows where no merchant name could be found: **{missing[1] or 0}**")

recent = pd.read_sql_query(
    """SELECT m.corrected_at AS changed_at, t.normalized_merchant AS merchant, m.field, m.old_value, m.new_value
       FROM manual_corrections m JOIN transactions t ON t.id = m.transaction_id
       ORDER BY m.id DESC LIMIT 20""", conn)
st.markdown("### Manual corrections")
if recent.empty:
    st.caption("No manual corrections yet.")
else:
    st.dataframe(recent, hide_index=True, width="stretch")
