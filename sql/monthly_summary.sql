-- Monthly cash-flow summary.
-- Concepts: WITH RECURSIVE (calendar of months so empty months show as 0),
--           conditional aggregation (CASE inside SUM), LEFT JOIN, LAG() and running
--           SUM() windows over a named WINDOW, EXISTS sub-queries.
-- Metric definitions: src/metrics.py ({{is_expense}} etc.) — see README "Financial metric definitions".
--
-- A month with no rows can mean two different things:
--   * it is covered by an imported statement  -> genuine zero spending      (is_covered = 1)
--   * no statement covers it                   -> missing data, not a zero  (is_covered = 0)
-- prev_status makes that explicit for the month-over-month comparison.
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
        SUM(CASE WHEN {{is_expense}} THEN amount_paise ELSE 0 END)
                                                                                                AS expenditure_paise,
        SUM(CASE WHEN {{is_refund}} THEN amount_paise ELSE 0 END)
                                                                                                AS refunds_paise,
        SUM(CASE WHEN {{is_income}} THEN amount_paise ELSE 0 END)
                                                                                                AS income_paise,
        SUM(CASE WHEN {{is_transfer}} THEN amount_paise ELSE 0 END)               AS transfers_paise,
        SUM(CASE WHEN {{is_cc_repayment}} THEN amount_paise ELSE 0 END)           AS cc_repayments_paise,
        SUM({{cash_flow_paise}})                                                                    AS net_cash_flow_paise,
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
),
coverage AS (
    SELECT m.month_start,
           EXISTS (SELECT 1 FROM statements s
                   WHERE s.statement_period_start <= date(m.month_start, '+1 month', '-1 day')
                     AND s.statement_period_end   >= m.month_start)                AS is_covered,
           -- fully covered when the statements' overall span contains the whole month
           (SELECT MIN(statement_period_start) <= m.month_start
                   AND MAX(statement_period_end) >= date(m.month_start, '+1 month', '-1 day')
            FROM statements)                                                        AS is_full_month
    FROM months AS m
),
ordered AS (
    SELECT f.*,
           c.is_covered,
           COALESCE(c.is_full_month, 0)                         AS is_full_month,
           LAG(f.month_start)       OVER w                      AS prev_month_start,
           LAG(f.expenditure_paise) OVER w                      AS prev_expenditure_paise,
           LAG(c.is_covered)        OVER w                      AS prev_is_covered,
           SUM(f.net_cash_flow_paise) OVER (w ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
                                                                AS cumulative_net_cash_flow_paise
    FROM filled AS f
    JOIN coverage AS c ON c.month_start = f.month_start
    WINDOW w AS (ORDER BY f.month_start)
)
SELECT
    o.*,
    CASE
        WHEN o.prev_month_start IS NULL THEN 'none'          -- first month in view
        WHEN o.prev_is_covered = 0      THEN 'not_covered'   -- previous month has no statement
        WHEN o.prev_expenditure_paise = 0 THEN 'zero'        -- previous month genuinely had no spending
        ELSE 'value'
    END AS prev_status,
    -- Absolute change only when both months are real data.
    CASE WHEN o.prev_month_start IS NOT NULL AND o.prev_is_covered = 1 AND o.is_covered = 1
         THEN o.expenditure_paise - o.prev_expenditure_paise END AS expenditure_change_paise,
    -- Month-over-month compares Expenditure (before refunds) so the change can be
    -- broken down by category. NULL when there is no comparable, non-zero previous month.
    CASE
        WHEN o.prev_is_covered = 1 AND o.is_covered = 1 AND o.prev_expenditure_paise > 0
        THEN ROUND(100.0 * (o.expenditure_paise - o.prev_expenditure_paise) / o.prev_expenditure_paise, 1)
    END AS mom_change_pct
FROM ordered AS o
ORDER BY o.month_start;
