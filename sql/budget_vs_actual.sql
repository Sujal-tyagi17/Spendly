-- Category budgets vs actual expenditure for one month.
-- Answers: "Where am I over or under budget this month, and by how much?"
--
-- Conventions (README → "Budget planner"):
--   actual       = Expenditure ({{is_expense}}), the same definition used everywhere else.
--                  Refunds are NOT netted per category: a refund carries category "Refunds",
--                  so it can't be reliably attributed to the category it reverses.
--   variance     = actual − budget        (positive = over budget)
--   remaining    = budget − actual        (negative = overspent)
--   utilisation  = actual / budget × 100  (NULL when the budget is 0)
-- Categories with spending but no budget are returned too (budget NULL), so nothing is hidden.
-- Concepts: LEFT JOIN + UNION ALL anti-join, NULLIF-safe ratios, parameters.
WITH
spend AS (
    SELECT category, SUM(amount_paise) AS actual_paise, COUNT(*) AS transaction_count
    FROM transactions
    WHERE transaction_date BETWEEN :month_start AND :month_end AND {{is_expense}}
    GROUP BY category
),
month_budgets AS (
    SELECT id, category, amount_paise FROM budgets
    WHERE month = :month_start AND category IS NOT NULL
),
combined AS (
    SELECT b.id AS budget_id, b.category, b.amount_paise AS budget_paise,
           COALESCE(s.actual_paise, 0) AS actual_paise, COALESCE(s.transaction_count, 0) AS transaction_count
    FROM month_budgets b
    LEFT JOIN spend s ON s.category = b.category
    UNION ALL
    SELECT NULL, s.category, NULL, s.actual_paise, s.transaction_count
    FROM spend s
    WHERE s.category NOT IN (SELECT category FROM month_budgets)
)
SELECT
    category,
    budget_id,
    budget_paise,
    actual_paise,
    transaction_count,
    budget_paise - actual_paise                                              AS remaining_paise,
    actual_paise - budget_paise                                              AS variance_paise,
    CASE WHEN budget_paise > 0 THEN ROUND(100.0 * actual_paise / budget_paise, 1) END                  AS utilisation_pct,
    CASE WHEN budget_paise > 0 THEN ROUND(100.0 * (actual_paise - budget_paise) / budget_paise, 1) END AS variance_pct
FROM combined
ORDER BY budget_paise IS NULL, (actual_paise - COALESCE(budget_paise, 0)) DESC, category;
