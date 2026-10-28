-- Weekday vs weekend spending, overall and per category.
-- Answers: "Do I spend differently on weekends?" (a description, not a cause).
-- Weekend totals are naturally smaller (2 days vs 5), so the query also counts the
-- calendar weekdays/weekend days in the period (:range_start – :range_end) and
-- returns spending PER DAY, which is the fair comparison.
-- Concepts: recursive date calendar, conditional aggregation, GROUPING via UNION ALL.
WITH RECURSIVE
base AS (
    SELECT * FROM transactions WHERE 1 = 1 /*FILTERS*/
),
days(d) AS (
    SELECT date(:range_start) WHERE :range_start IS NOT NULL
    UNION ALL
    SELECT date(d, '+1 day') FROM days WHERE d < date(:range_end)
),
day_counts AS (
    SELECT SUM(CASE WHEN CAST(strftime('%w', d) AS INTEGER) IN (0, 6) THEN 0 ELSE 1 END) AS weekday_days,
           SUM(CASE WHEN CAST(strftime('%w', d) AS INTEGER) IN (0, 6) THEN 1 ELSE 0 END) AS weekend_days
    FROM days
),
spend AS (
    SELECT category, amount_paise, {{is_weekend}} AS is_weekend
    FROM base WHERE {{is_expense}}
),
split AS (
    SELECT 'All categories' AS scope, 0 AS sort_key,
           SUM(CASE WHEN is_weekend = 0 THEN amount_paise ELSE 0 END) AS weekday_paise,
           SUM(CASE WHEN is_weekend = 1 THEN amount_paise ELSE 0 END) AS weekend_paise,
           SUM(CASE WHEN is_weekend = 0 THEN 1 ELSE 0 END)            AS weekday_txns,
           SUM(CASE WHEN is_weekend = 1 THEN 1 ELSE 0 END)            AS weekend_txns
    FROM spend
    UNION ALL
    SELECT category, 1,
           SUM(CASE WHEN is_weekend = 0 THEN amount_paise ELSE 0 END),
           SUM(CASE WHEN is_weekend = 1 THEN amount_paise ELSE 0 END),
           SUM(CASE WHEN is_weekend = 0 THEN 1 ELSE 0 END),
           SUM(CASE WHEN is_weekend = 1 THEN 1 ELSE 0 END)
    FROM spend GROUP BY category
)
SELECT s.scope,
       COALESCE(s.weekday_paise, 0) AS weekday_paise,
       COALESCE(s.weekend_paise, 0) AS weekend_paise,
       COALESCE(s.weekday_txns, 0)  AS weekday_txns,
       COALESCE(s.weekend_txns, 0)  AS weekend_txns,
       c.weekday_days,
       c.weekend_days,
       CAST(ROUND(1.0 * s.weekday_paise / NULLIF(s.weekday_txns, 0)) AS INTEGER) AS weekday_avg_txn_paise,
       CAST(ROUND(1.0 * s.weekend_paise / NULLIF(s.weekend_txns, 0)) AS INTEGER) AS weekend_avg_txn_paise,
       CAST(ROUND(1.0 * s.weekday_paise / NULLIF(c.weekday_days, 0)) AS INTEGER) AS weekday_per_day_paise,
       CAST(ROUND(1.0 * s.weekend_paise / NULLIF(c.weekend_days, 0)) AS INTEGER) AS weekend_per_day_paise,
       ROUND(100.0 * s.weekend_paise / NULLIF(s.weekday_paise + s.weekend_paise, 0), 1) AS weekend_share_pct
FROM split s CROSS JOIN day_counts c
WHERE s.scope = 'All categories' OR s.weekday_paise + s.weekend_paise > 0
ORDER BY s.sort_key, s.weekday_paise + s.weekend_paise DESC, s.scope;
