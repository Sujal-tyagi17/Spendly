-- Raw material for the recurring-payment detector.
-- For merchants paid at least :min_occurrences times, return every payment with
-- the number of days since the previous payment to the same merchant (LAG over
-- julianday). Python then checks the intervals against weekly/monthly/... schedules.
WITH base AS (
    SELECT * FROM transactions WHERE 1 = 1 /*FILTERS*/
),
payments AS (
    SELECT id, normalized_merchant AS merchant, category, transaction_date, amount_paise,
           COUNT(*) OVER (PARTITION BY normalized_merchant) AS occurrences
    FROM base
    WHERE direction = 'debit' AND transaction_type IN ('expense', 'other')
)
SELECT id, merchant, category, transaction_date, amount_paise, occurrences,
       CAST(julianday(transaction_date)
            - julianday(LAG(transaction_date) OVER (PARTITION BY merchant ORDER BY transaction_date, id))
            AS INTEGER) AS days_since_previous
FROM payments
WHERE occurrences >= :min_occurrences
ORDER BY merchant, transaction_date, id;
