-- Largest individual expenses in the period.
WITH base AS (
    SELECT * FROM transactions WHERE 1 = 1 /*FILTERS*/
)
SELECT id, transaction_date, normalized_merchant AS merchant, category, amount_paise, description
FROM base
WHERE transaction_type = 'expense' AND direction = 'debit'
ORDER BY amount_paise DESC, transaction_date DESC
LIMIT :limit;
