-- Headline KPIs for the selected period, in one pass over the data.
WITH base AS (
    SELECT * FROM transactions WHERE 1 = 1 /*FILTERS*/
)
SELECT
    COUNT(*)                                                                                  AS transaction_count,
    MIN(transaction_date)                                                                     AS first_date,
    MAX(transaction_date)                                                                     AS last_date,
    COALESCE(SUM(CASE WHEN direction = 'debit' THEN amount_paise END), 0)                      AS gross_debits_paise,
    COALESCE(SUM(CASE WHEN direction = 'credit' THEN amount_paise END), 0)                     AS total_credits_paise,
    COALESCE(SUM(CASE WHEN {{is_expense}} THEN amount_paise END), 0)
                                                                                              AS expenditure_paise,
    COALESCE(SUM(CASE WHEN {{is_refund}} THEN amount_paise END), 0)
                                                                                              AS refunds_paise,
    COALESCE(SUM(CASE WHEN {{is_income}} THEN amount_paise END), 0)
                                                                                              AS income_paise,
    COALESCE(SUM(CASE WHEN {{is_transfer}} THEN amount_paise END), 0)            AS transfers_paise,
    COALESCE(SUM(CASE WHEN {{is_cc_repayment}} THEN amount_paise END), 0)        AS cc_repayments_paise,
    COALESCE(SUM({{cash_flow_paise}}), 0)
                                                                                              AS net_cash_flow_paise,
    SUM(CASE WHEN categorization_method = 'none' THEN 1 ELSE 0 END)                           AS uncategorized_count,
    COALESCE(SUM(CASE WHEN categorization_method = 'none' AND direction = 'debit' THEN amount_paise END), 0)
                                                                                              AS uncategorized_debits_paise,
    SUM(CASE WHEN review_status = 'needs_review' THEN 1 ELSE 0 END)                           AS needs_review_count,
    SUM(is_possible_duplicate)                                                                AS possible_duplicate_count
FROM base;
