-- Expenditure per month per category (for the month-over-month comparison chart).
WITH base AS (
    SELECT * FROM transactions WHERE 1 = 1 /*FILTERS*/
)
SELECT date(transaction_date, 'start of month') AS month_start,
       category,
       SUM(amount_paise)                        AS expenditure_paise,
       COUNT(*)                                 AS transaction_count
FROM base
WHERE transaction_type = 'expense' AND direction = 'debit'
GROUP BY 1, 2
ORDER BY 1, 3 DESC;
