-- Overall picture for one month: overall budget, sum of category budgets, and actual totals.
WITH
month_spend AS (
    SELECT
        COALESCE(SUM(CASE WHEN {{is_expense}} THEN amount_paise END), 0) AS expenditure_paise,
        COALESCE(SUM(CASE WHEN {{is_refund}} THEN amount_paise END), 0)  AS refunds_paise,
        SUM(CASE WHEN {{is_expense}} THEN 1 ELSE 0 END)                  AS expense_count
    FROM transactions
    WHERE transaction_date BETWEEN :month_start AND :month_end
),
budgeted_categories AS (
    SELECT category FROM budgets WHERE month = :month_start AND category IS NOT NULL
)
SELECT
    (SELECT id FROM budgets WHERE month = :month_start AND category IS NULL)            AS overall_budget_id,
    (SELECT amount_paise FROM budgets WHERE month = :month_start AND category IS NULL)  AS overall_budget_paise,
    (SELECT COALESCE(SUM(amount_paise), 0) FROM budgets
      WHERE month = :month_start AND category IS NOT NULL)                              AS category_budgets_paise,
    (SELECT COUNT(*) FROM budgeted_categories)                                          AS budgeted_category_count,
    m.expenditure_paise,
    m.refunds_paise,
    m.expenditure_paise - m.refunds_paise                                               AS net_expenditure_paise,
    COALESCE(m.expense_count, 0)                                                        AS expense_count,
    -- spending in categories that have no budget this month
    (SELECT COALESCE(SUM(amount_paise), 0) FROM transactions
      WHERE transaction_date BETWEEN :month_start AND :month_end AND {{is_expense}}
        AND category NOT IN (SELECT category FROM budgeted_categories))                 AS unbudgeted_paise
FROM month_spend m;
