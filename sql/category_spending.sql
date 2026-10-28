-- Expenditure by category with share of total and average ticket size.
-- Concepts: aggregate + window functions over the aggregate (SUM() OVER (), RANK()).
WITH base AS (
    SELECT * FROM transactions WHERE 1 = 1 /*FILTERS*/
),
spend AS (
    SELECT category,
           COUNT(*)          AS transaction_count,
           SUM(amount_paise) AS expenditure_paise
    FROM base
    WHERE {{is_expense}}
    GROUP BY category
)
SELECT
    category,
    transaction_count,
    expenditure_paise,
    CAST(ROUND(1.0 * expenditure_paise / transaction_count) AS INTEGER)          AS avg_transaction_paise,
    ROUND(100.0 * expenditure_paise / NULLIF(SUM(expenditure_paise) OVER (), 0), 1) AS share_pct,
    RANK() OVER (ORDER BY expenditure_paise DESC)                                AS spend_rank
FROM spend
ORDER BY expenditure_paise DESC, category;
