-- Transactions no rule could categorize, grouped by merchant so one fix covers many rows.
WITH base AS (
    SELECT * FROM transactions WHERE 1 = 1 /*FILTERS*/
)
SELECT normalized_merchant AS merchant,
       direction,
       COUNT(*)            AS transaction_count,
       SUM(amount_paise)   AS total_paise,
       MAX(transaction_date) AS last_seen
FROM base
WHERE categorization_method = 'none'
GROUP BY normalized_merchant, direction
ORDER BY transaction_count DESC, total_paise DESC;
