-- Category spending month by month, with each category's own month-over-month change.
-- Answers: "Which categories drove this month's change, and how does each one trend?"
-- Concepts: recursive month calendar CROSS JOIN categories (so a category with no spending
--           in a month shows 0 instead of disappearing), LAG() PARTITION BY category,
--           share of the month via SUM() OVER (PARTITION BY month), DENSE_RANK() per month,
--           and each category's share of the month's total change.
WITH RECURSIVE
base AS (
    SELECT * FROM transactions WHERE 1 = 1 /*FILTERS*/
),
bounds AS (
    SELECT date(MIN(transaction_date), 'start of month') AS first_month,
           date(MAX(transaction_date), 'start of month') AS last_month
    FROM base
),
months(month_start) AS (
    SELECT first_month FROM bounds WHERE first_month IS NOT NULL
    UNION ALL
    SELECT date(month_start, '+1 month') FROM months, bounds WHERE month_start < bounds.last_month
),
spend AS (
    SELECT date(transaction_date, 'start of month') AS month_start,
           category,
           SUM(amount_paise) AS expenditure_paise,
           COUNT(*)          AS transaction_count
    FROM base
    WHERE {{is_expense}}
    GROUP BY 1, 2
),
cats AS (SELECT DISTINCT category FROM spend),
grid AS (
    SELECT m.month_start, c.category,
           COALESCE(s.expenditure_paise, 0) AS expenditure_paise,
           COALESCE(s.transaction_count, 0) AS transaction_count
    FROM months m CROSS JOIN cats c
    LEFT JOIN spend s ON s.month_start = m.month_start AND s.category = c.category
),
measured AS (
    SELECT g.*,
           LAG(g.expenditure_paise) OVER (PARTITION BY g.category ORDER BY g.month_start) AS prev_expenditure_paise,
           SUM(g.expenditure_paise) OVER (PARTITION BY g.month_start)                    AS month_total_paise
    FROM grid g
),
changes AS (
    SELECT m.*,
           m.expenditure_paise - m.prev_expenditure_paise AS change_paise,
           SUM(m.expenditure_paise - m.prev_expenditure_paise) OVER (PARTITION BY m.month_start) AS month_change_paise
    FROM measured m
)
SELECT month_start,
       category,
       expenditure_paise,
       transaction_count,
       prev_expenditure_paise,                                   -- NULL in the first month
       change_paise,
       CASE WHEN prev_expenditure_paise > 0
            THEN ROUND(100.0 * change_paise / prev_expenditure_paise, 1) END AS change_pct,
       ROUND(100.0 * expenditure_paise / NULLIF(month_total_paise, 0), 1)   AS share_of_month_pct,
       -- Share of the month's overall change explained by this category (signed).
       CASE WHEN month_change_paise <> 0
            THEN ROUND(100.0 * change_paise / month_change_paise, 1) END   AS share_of_change_pct,
       DENSE_RANK() OVER (PARTITION BY month_start ORDER BY expenditure_paise DESC) AS rank_in_month
FROM changes
ORDER BY month_start, expenditure_paise DESC, category;
