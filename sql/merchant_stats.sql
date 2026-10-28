-- Merchant analysis: how much, how often, typical ticket size and concentration.
-- Answers: "Who gets my money, how often do I pay them, and what's a normal payment?"
-- Concepts: ROW_NUMBER() + COUNT() OVER (PARTITION BY) to compute a MEDIAN in SQLite
--           (which has no MEDIAN function), RANK() vs DENSE_RANK(), and a running total
--           (SUM() OVER ORDER BY ... ROWS UNBOUNDED PRECEDING) for cumulative share.
WITH base AS (
    SELECT * FROM transactions WHERE 1 = 1 /*FILTERS*/
),
spend AS (
    SELECT normalized_merchant AS merchant, category, transaction_date, amount_paise
    FROM base
    WHERE {{is_expense}}
),
ordered AS (
    SELECT merchant, amount_paise,
           ROW_NUMBER() OVER (PARTITION BY merchant ORDER BY amount_paise) AS rn,
           COUNT(*)     OVER (PARTITION BY merchant)                       AS n
    FROM spend
),
medians AS (
    -- middle value (odd n) or mean of the two middle values (even n)
    SELECT merchant, AVG(amount_paise) AS median_paise
    FROM ordered
    WHERE rn IN ((n + 1) / 2, (n + 2) / 2)
    GROUP BY merchant
),
per_merchant AS (
    SELECT merchant,
           MAX(category)                                   AS category,
           COUNT(*)                                        AS transaction_count,
           SUM(amount_paise)                               AS expenditure_paise,
           MIN(transaction_date)                           AS first_seen,
           MAX(transaction_date)                           AS last_seen,
           COUNT(DISTINCT strftime('%Y-%m', transaction_date)) AS active_months
    FROM spend
    GROUP BY merchant
)
SELECT p.merchant,
       p.category,
       p.transaction_count,
       p.expenditure_paise,
       CAST(ROUND(1.0 * p.expenditure_paise / p.transaction_count) AS INTEGER) AS avg_transaction_paise,
       CAST(ROUND(m.median_paise) AS INTEGER)                                  AS median_transaction_paise,
       p.first_seen,
       p.last_seen,
       p.active_months,
       ROUND(100.0 * p.expenditure_paise / NULLIF(SUM(p.expenditure_paise) OVER (), 0), 2) AS share_pct,
       ROUND(100.0 * SUM(p.expenditure_paise) OVER (ORDER BY p.expenditure_paise DESC, p.merchant
                                                   ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
             / NULLIF(SUM(p.expenditure_paise) OVER (), 0), 2)                   AS cumulative_share_pct,
       RANK()       OVER (ORDER BY p.expenditure_paise DESC)                     AS spend_rank,
       DENSE_RANK() OVER (ORDER BY p.transaction_count DESC)                     AS frequency_rank
FROM per_merchant p
JOIN medians m ON m.merchant = p.merchant
ORDER BY p.expenditure_paise DESC, p.merchant;
