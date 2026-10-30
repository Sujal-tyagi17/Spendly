# SQL showcase

Six queries from [`sql/`](../sql), each answering a question a stakeholder would actually ask. Every number below
comes from running the query on the synthetic demo dataset (Apr–Sep 2026, 284 transactions). The snippets are
excerpts; the linked files are complete and commented.

All amounts are stored as integer paise. "Expenditure" means spending debits only: transfers between your own
accounts and credit-card bill payments are excluded, and refunds are reported separately
([`src/metrics.py`](../src/metrics.py) holds the single definition every query uses).

---

## 1. Did spending go up or down, month by month? (`LAG`, recursive calendar)

**Question.** How did each month compare with the one before, and is a "drop" real or just a missing statement?
**File.** [`sql/monthly_summary.sql`](../sql/monthly_summary.sql)

```sql
WITH RECURSIVE months(month_start) AS (            -- every month in range, even empty ones
    SELECT first_month FROM bounds
    UNION ALL SELECT date(month_start, '+1 month') FROM months, bounds WHERE month_start < bounds.last_month
)
...
LAG(f.expenditure_paise) OVER w  AS prev_expenditure_paise,
LAG(c.is_covered)        OVER w  AS prev_is_covered,       -- was last month covered by a statement?
SUM(f.net_cash_flow_paise) OVER (w ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_net_cash_flow_paise
...
WINDOW w AS (ORDER BY f.month_start)
```

| Month | Expenditure | Previous | Change | Running net cash flow |
|---|---:|---:|---:|---:|
| Jul 2026 | ₹43,054 | ₹51,507 | −16.4% | ₹50,884 |
| Aug 2026 | ₹1,02,186 | ₹43,054 | +137.3% | ₹8,448 |
| Sep 2026 | ₹40,088 | ₹1,02,186 | −60.8% | ₹26,830 |

**What it means.** August more than doubled, and the running cash flow nearly wiped out four months of savings.
**Why it matters.** A month with no statement is marked `not_covered` instead of being compared as ₹0, so the
query can never report a fake 100% drop.

## 2. Which categories drove the change? (`LAG … PARTITION BY`, share of change)

**Question.** This month changed by ₹X. How much of that came from each category?
**File.** [`sql/monthly_category.sql`](../sql/monthly_category.sql)

```sql
LAG(g.expenditure_paise) OVER (PARTITION BY g.category ORDER BY g.month_start) AS prev_expenditure_paise,
SUM(m.expenditure_paise - m.prev_expenditure_paise) OVER (PARTITION BY m.month_start) AS month_change_paise,
ROUND(100.0 * change_paise / month_change_paise, 1)                               AS share_of_change_pct,
DENSE_RANK() OVER (PARTITION BY month_start ORDER BY expenditure_paise DESC)      AS rank_in_month
```

A calendar of months is `CROSS JOIN`ed with the categories, so a category with no spending in a month shows ₹0
instead of disappearing (which would hide a 100% drop).

**What it means.** In September, Shopping fell by ₹57,468 and accounts for most of the 60.8% drop; Groceries
rose 24.2% but was a small part of the change.
**Why it matters.** It turns "spending fell" into "spending fell because of one category", which is the first
question a manager asks.

## 3. Who gets the money, and what's a normal payment? (median in SQLite, `RANK` vs `DENSE_RANK`, running share)

**Question.** Which merchants matter most, and is the average payment misleading?
**File.** [`sql/merchant_stats.sql`](../sql/merchant_stats.sql)

```sql
ROW_NUMBER() OVER (PARTITION BY merchant ORDER BY amount_paise) AS rn,
COUNT(*)     OVER (PARTITION BY merchant)                       AS n
...                                       -- SQLite has no MEDIAN(): average the middle row(s)
SUM(p.expenditure_paise) OVER (ORDER BY p.expenditure_paise DESC ROWS UNBOUNDED PRECEDING)
    / SUM(p.expenditure_paise) OVER ()                          AS cumulative_share_pct,
RANK()       OVER (ORDER BY p.expenditure_paise DESC)           AS spend_rank,
DENSE_RANK() OVER (ORDER BY p.transaction_count DESC)           AS frequency_rank
```

| Merchant | Payments | Total | Average | Median | Cumulative share |
|---|---:|---:|---:|---:|---:|
| House Rent | 6 | ₹1,08,000 | ₹18,000 | ₹18,000 | 33.2% |
| Amazon | 6 | ₹63,431 | ₹10,572 | ₹1,949 | 52.7% |
| Zomato | 36 | ₹13,570 | ₹377 | ₹355 | 56.8% |

**What it means.** Amazon's average (₹10,572 = ₹63,431 ÷ 6 purchases) is more than five times its median (₹1,949,
the mean of the middle two payments, ₹1,743 and ₹2,155) because of one ₹54,999 laptop. The ₹1,299 refund in July is
not a purchase, so it is excluded. All figures are from the synthetic demo dataset.
**Why it matters.** Reporting the median next to the average stops one outlier from distorting "a typical order".

## 4. Is spending concentrated in a few merchants? (ranking + Herfindahl–Hirschman index)

**Question.** Is the money spread out, or dominated by a handful of payees?
**File.** [`sql/spending_concentration.sql`](../sql/spending_concentration.sql)

```sql
ROUND((SELECT SUM(share) FROM ranked WHERE rn <= 5), 2)  AS top_5_share_pct,
ROUND((SELECT SUM(share * share) FROM ranked), 1)        AS hhi        -- 0–10,000
```

**Result.** 32 merchants; the top merchant takes 33.2%, the top 5 take 64.6%, and the HHI is 1,600
(moderate concentration).
**Why it matters.** It's the same concentration measure used for market share and supplier risk, applied to a
budget: a high HHI means a few decisions control most of the spending.

## 5. Do weekends cost more? (recursive date calendar, per-day normalisation)

**Question.** Is weekend spending higher, once you account for there being 5 weekdays and 2 weekend days?
**File.** [`sql/weekend_split.sql`](../sql/weekend_split.sql)

```sql
SUM(CASE WHEN CAST(strftime('%w', d) AS INTEGER) IN (0, 6) THEN 1 ELSE 0 END) AS weekend_days,
...
ROUND(1.0 * s.weekday_paise / NULLIF(c.weekday_days, 0)) AS weekday_per_day_paise,
ROUND(1.0 * s.weekend_paise / NULLIF(c.weekend_days, 0)) AS weekend_per_day_paise
```

**Result.** ₹1,979 per weekday vs ₹1,276 per weekend day; 20.4% of expenditure happened on weekends.
**Why it matters.** Comparing raw totals would always make weekdays look worse (131 days vs 52). Dividing by the
number of calendar days is the fair comparison, and the query reports it per category too.

## 6. What repeats on a schedule? (`LAG` over dates)

**Question.** Which payments are subscriptions or fixed bills, and when is the next one due?
**File.** [`sql/recurring_candidates.sql`](../sql/recurring_candidates.sql)

```sql
CAST(julianday(transaction_date)
     - julianday(LAG(transaction_date) OVER (PARTITION BY merchant ORDER BY transaction_date, id))
     AS INTEGER) AS days_since_previous
```

| Merchant | Payment dates | Days between |
|---|---|---|
| House Rent | 3 Apr, 3 May, 3 Jun, 3 Jul, 3 Aug, 3 Sep | 30, 31, 30, 31, 31 |

**What it means.** SQL supplies the gaps between payments; Python ([`src/subscription_detector.py`](../src/subscription_detector.py))
checks them against weekly, monthly, quarterly and yearly schedules and requires at least three payments.
**Why it matters.** Recurring costs are the part of a budget that is committed in advance. The demo finds 6
active recurring payments costing about ₹21,190 a month.

---

**Checked by tests.** `tests/test_advanced_analytics.py` recomputes the merchant medians, concentration and
weekend split in plain Python and asserts the SQL results match; `tests/test_qa_known_answer.py` checks a
hand-built statement against figures computed by hand.
