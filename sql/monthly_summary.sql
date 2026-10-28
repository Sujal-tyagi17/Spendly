-- Monthly cash-flow summary.
-- Concepts: WITH RECURSIVE (calendar of months so empty months show as 0),
--           conditional aggregation (CASE inside SUM), LEFT JOIN, LAG() window.
-- Metric definitions: see README "Financial metric definitions".
WITH RECURSIVE
base AS (
    SELECT * FROM transactions WHERE 1 = 1 /*FILTERS*/
),
bounds AS (
    SELECT date(MIN(transaction_date), 'start of month') AS first_month,
           date(MAX(transaction_date), 'start of month') AS last_month
    FROM base
),
months(month_start) AS (
    SELECT first_month FROM bounds WHERE first_month IS NOT NULL
    UNION ALL
    SELECT date(month_start, '+1 month')
    FROM months, bounds
    WHERE month_start < bounds.last_month
),
monthly AS (
    SELECT
        date(transaction_date, 'start of month')                                              AS month_start,
        SUM(CASE WHEN direction = 'debit' THEN amount_paise ELSE 0 END)                         AS gross_debits_paise,
        SUM(CASE WHEN direction = 'credit' THEN amount_paise ELSE 0 END)                        AS total_credits_paise,
        SUM(CASE WHEN transaction_type = 'expense' AND direction = 'debit' THEN amount_paise ELSE 0 END)
                                                                                                AS expenditure_paise,
        SUM(CASE WHEN transaction_type = 'refund' AND direction = 'credit' THEN amount_paise ELSE 0 END)
                                                                                                AS refunds_paise,
        SUM(CASE WHEN transaction_type = 'income' AND direction = 'credit' THEN amount_paise ELSE 0 END)
                                                                                                AS income_paise,
        SUM(CASE WHEN transaction_type = 'transfer' THEN amount_paise ELSE 0 END)               AS transfers_paise,
        SUM(CASE WHEN transaction_type = 'cc_repayment' THEN amount_paise ELSE 0 END)           AS cc_repayments_paise,
        SUM(CASE WHEN transaction_type <> 'transfer'
                 THEN CASE WHEN direction = 'credit' THEN amount_paise ELSE -amount_paise END
                 ELSE 0 END)                                                                    AS net_cash_flow_paise,
        COUNT(*)                                                                                AS transaction_count
    FROM base
    GROUP BY 1
),
filled AS (
    SELECT
        m.month_start,
        COALESCE(x.gross_debits_paise, 0)   AS gross_debits_paise,
        COALESCE(x.total_credits_paise, 0)  AS total_credits_paise,
        COALESCE(x.expenditure_paise, 0)    AS expenditure_paise,
        COALESCE(x.refunds_paise, 0)        AS refunds_paise,
        COALESCE(x.expenditure_paise, 0) - COALESCE(x.refunds_paise, 0) AS net_expenditure_paise,
        COALESCE(x.income_paise, 0)         AS income_paise,
        COALESCE(x.transfers_paise, 0)      AS transfers_paise,
        COALESCE(x.cc_repayments_paise, 0)  AS cc_repayments_paise,
        COALESCE(x.net_cash_flow_paise, 0)  AS net_cash_flow_paise,
        COALESCE(x.transaction_count, 0)    AS transaction_count
    FROM months AS m
    LEFT JOIN monthly AS x ON x.month_start = m.month_start
)
SELECT
    f.*,
    -- Month-over-month compares Expenditure (before refunds) so the change can be
    -- broken down by category on the Spending Insights page.
    LAG(f.expenditure_paise) OVER (ORDER BY f.month_start) AS prev_expenditure_paise,
    CASE
        WHEN LAG(f.expenditure_paise) OVER (ORDER BY f.month_start) > 0
        THEN ROUND(100.0 * (f.expenditure_paise - LAG(f.expenditure_paise) OVER (ORDER BY f.month_start))
                   / LAG(f.expenditure_paise) OVER (ORDER BY f.month_start), 1)
    END AS mom_change_pct            -- NULL when there is no (or a zero) previous month
FROM filled AS f
ORDER BY f.month_start;
