-- Merchants that receive the most money (expenses only).
WITH base AS (
    SELECT * FROM transactions WHERE 1 = 1 /*FILTERS*/
),
by_merchant AS (
    SELECT normalized_merchant  AS merchant,
           MAX(category)        AS category,   -- a merchant normally has one category
           COUNT(*)             AS transaction_count,
           SUM(amount_paise)    AS expenditure_paise,
           MAX(transaction_date) AS last_seen
    FROM base
    WHERE transaction_type = 'expense' AND direction = 'debit'
    GROUP BY normalized_merchant
)
SELECT merchant, category, transaction_count, expenditure_paise, last_seen,
       ROUND(100.0 * expenditure_paise / NULLIF(SUM(expenditure_paise) OVER (), 0), 1) AS share_pct,
       RANK() OVER (ORDER BY expenditure_paise DESC) AS spend_rank
FROM by_merchant
ORDER BY expenditure_paise DESC, merchant
LIMIT :limit;
