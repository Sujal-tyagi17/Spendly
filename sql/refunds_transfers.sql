-- Monthly refund and internal-transfer totals (both excluded from spending).
WITH base AS (
    SELECT * FROM transactions WHERE 1 = 1 /*FILTERS*/
)
SELECT date(transaction_date, 'start of month') AS month_start,
       SUM(CASE WHEN transaction_type = 'refund' THEN amount_paise ELSE 0 END)                         AS refunds_paise,
       SUM(CASE WHEN transaction_type = 'transfer' AND direction = 'debit' THEN amount_paise ELSE 0 END) AS transfers_out_paise,
       SUM(CASE WHEN transaction_type = 'transfer' AND direction = 'credit' THEN amount_paise ELSE 0 END) AS transfers_in_paise,
       SUM(CASE WHEN transaction_type = 'cc_repayment' THEN amount_paise ELSE 0 END)                   AS cc_repayments_paise
FROM base
WHERE transaction_type IN ('refund', 'transfer', 'cc_repayment')
GROUP BY 1
ORDER BY 1;
