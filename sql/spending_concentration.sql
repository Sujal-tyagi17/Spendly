-- How concentrated is spending? One row of summary measures.
-- Answers: "Is my spending spread across many merchants or dominated by a few?"
--   top_N_share_pct   share of expenditure going to the N largest merchants
--   hhi               Herfindahl–Hirschman index = sum of squared % shares (0–10,000);
--                     higher = more concentrated. 10,000 means a single merchant.
-- Concepts: RANK() then conditional aggregation over the ranked rows.
WITH base AS (
    SELECT * FROM transactions WHERE 1 = 1 /*FILTERS*/
),
merchants AS (
    SELECT normalized_merchant AS merchant, SUM(amount_paise) AS spend
    FROM base WHERE {{is_expense}}
    GROUP BY normalized_merchant
),
ranked AS (
    SELECT merchant, spend,
           ROW_NUMBER() OVER (ORDER BY spend DESC, merchant)       AS rn,
           100.0 * spend / NULLIF(SUM(spend) OVER (), 0)           AS share
    FROM merchants
),
categories AS (
    SELECT category, SUM(amount_paise) AS spend
    FROM base WHERE {{is_expense}}
    GROUP BY category
)
SELECT
    (SELECT COUNT(*) FROM merchants)                                            AS merchant_count,
    (SELECT COALESCE(SUM(spend), 0) FROM merchants)                             AS expenditure_paise,
    ROUND((SELECT SUM(share) FROM ranked WHERE rn <= 1), 2)                     AS top_1_share_pct,
    ROUND((SELECT SUM(share) FROM ranked WHERE rn <= 5), 2)                     AS top_5_share_pct,
    ROUND((SELECT SUM(share) FROM ranked WHERE rn <= 10), 2)                    AS top_10_share_pct,
    ROUND((SELECT SUM(share * share) FROM ranked), 1)                           AS hhi,
    (SELECT merchant FROM ranked WHERE rn = 1)                                  AS top_merchant,
    (SELECT COUNT(*) FROM categories)                                           AS category_count,
    (SELECT category FROM categories ORDER BY spend DESC, category LIMIT 1)     AS top_category,
    ROUND((SELECT 100.0 * MAX(spend) / NULLIF(SUM(spend), 0) FROM categories), 2) AS top_category_share_pct;
