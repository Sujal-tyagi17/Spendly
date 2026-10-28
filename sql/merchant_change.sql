-- Merchant expenditure in the current vs previous period (same shape as category_change.sql).
WITH base AS (
    SELECT * FROM transactions WHERE 1 = 1 /*FILTERS*/
),
periods AS (
    SELECT normalized_merchant AS merchant,
           SUM(CASE WHEN transaction_date BETWEEN :cur_start AND :cur_end THEN amount_paise ELSE 0 END)   AS current_paise,
           SUM(CASE WHEN transaction_date BETWEEN :prev_start AND :prev_end THEN amount_paise ELSE 0 END) AS previous_paise
    FROM base
    WHERE transaction_type = 'expense' AND direction = 'debit'
      AND transaction_date BETWEEN :prev_start AND :cur_end
    GROUP BY normalized_merchant
)
SELECT merchant, current_paise, previous_paise,
       current_paise - previous_paise AS change_paise,
       CASE WHEN previous_paise > 0
            THEN ROUND(100.0 * (current_paise - previous_paise) / previous_paise, 1) END AS change_pct
FROM periods
ORDER BY change_paise DESC, merchant;
