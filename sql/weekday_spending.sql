-- Spending by day of week. A VALUES list provides all 7 days so quiet days show 0.
-- strftime('%w') returns 0 = Sunday ... 6 = Saturday.
WITH base AS (
    SELECT * FROM transactions WHERE 1 = 1 /*FILTERS*/
),
weekdays(weekday_num, weekday_name) AS (
    VALUES (1, 'Monday'), (2, 'Tuesday'), (3, 'Wednesday'), (4, 'Thursday'),
           (5, 'Friday'), (6, 'Saturday'), (0, 'Sunday')
),
spend AS (
    SELECT CAST(strftime('%w', transaction_date) AS INTEGER) AS weekday_num,
           COUNT(*)                                          AS transaction_count,
           SUM(amount_paise)                                 AS expenditure_paise,
           COUNT(DISTINCT transaction_date)                  AS active_days
    FROM base
    WHERE transaction_type = 'expense' AND direction = 'debit'
    GROUP BY 1
)
SELECT w.weekday_num,
       w.weekday_name,
       COALESCE(s.transaction_count, 0) AS transaction_count,
       COALESCE(s.expenditure_paise, 0) AS expenditure_paise,
       CAST(ROUND(1.0 * s.expenditure_paise / NULLIF(s.transaction_count, 0)) AS INTEGER) AS avg_transaction_paise
FROM weekdays AS w
LEFT JOIN spend AS s ON s.weekday_num = w.weekday_num
ORDER BY CASE w.weekday_num WHEN 0 THEN 7 ELSE w.weekday_num END;
