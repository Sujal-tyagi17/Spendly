# Spendly: interview guide

These are the questions an interviewer is most likely to ask about Spendly, with answers that match how the
code actually works. Open the file each answer points to, so you can show the interviewer, not just tell them.

## The 30-second pitch

> "Spendly turns UPI and bank statement PDFs into a spending dashboard. I extract the transactions with
> pdfplumber and clean them in pandas: dates, amounts stored in paise, and merchant names. Each import is checked
> with a running-balance test. The rows are categorized with a config-driven rule engine and stored in SQLite.
> All the metrics are calculated in SQL with CTEs and window functions. The app explains *why* spending changed,
> detects subscriptions, and flags unusual payments, and every one of those has a plain-English reason."

## Data extraction

**1. How do you get data out of a PDF?**
`src/pdf_parser.py`. Each statement layout has its own parser class with `can_parse()` and `parse()`.
The bank parser uses `pdfplumber.extract_tables()`. It finds the header row by matching column names against a
synonym list (for example "Narration", "Description" or "Particulars"), so it doesn't rely on fixed column
positions. The PhonePe parser reads text lines with a regex.

**2. What happens with a statement format you don't support?**
The user gets a clear error that lists the supported formats. I don't use a "parse anything" fallback, because
wrong numbers are worse than no numbers. Adding a format means adding one class to `PARSERS`.

**3. Multi-page statements and long descriptions?**
Header rows that repeat on every page are recognised and skipped. A row with no date and no amount but some text
is a wrapped description, so it gets joined to the row above.

**4. Scanned or password-protected PDFs?**
If a PDF has almost no extractable text, it's scanned, and the app explains that OCR isn't supported.
Password-protected PDFs open with the password the user types. The password is never stored.

## Cleaning and validation

**5. Why store money as paise integers instead of floats?**
In floating point, `0.1 + 0.2` isn't exactly `0.3`. Text is parsed with `Decimal` and stored as integer paise,
so sums are always exact. See `src/money.py` and `test_amounts_have_no_float_rounding_error`.

**6. How do you handle dates like 03/04/2026?**
Each parser declares the date formats it uses. Indian statements are day-first. If two declared formats would
give different dates for the same text, the row is flagged as ambiguous instead of guessed.

**7. How do you know the extraction is correct?**
With the running-balance check in `src/data_validator.py`. For consecutive rows,
`previous balance − debit + credit` must equal the printed balance. A mismatch means a row was misread or is
missing. The check runs in both directions because some banks print newest-first. The Data Quality page shows
the match rate.

**8. How did you handle duplicates?**
There are two levels (`src/duplicates.py`):
- **Exact duplicate**: same date, amount, description, and also the same running balance or transaction ID.
  Two real payments can't leave the same balance, so this is a repeated row or an overlapping statement. These
  are skipped.
- **Possible duplicate**: same date, amount and merchant, but no strong key. Two ₹20 chai payments on one day are
  normal, so these rows are imported and flagged, never deleted automatically.

Re-uploading the exact same file is blocked by its SHA-256 hash.

**9. How do you normalize merchant names?**
`src/merchant_normalizer.py` first removes reference numbers, UPI IDs and suffixes like `*ORDER123`. Then it
matches alias patterns from `config/rules.json`. If nothing matches, it uses the first meaningful part of the UPI
string. I deliberately don't use fuzzy matching, because "Amazon" and "Amazing Bakery" are similar strings but
different businesses.

## Categorization

**10. How did you decide categories, and what if a rule is wrong?**
It's rule-first, and the order is:
1. Type rules: transfer, card bill, refund, salary, rent.
2. Direction: a debit becomes an expense. A credit is NOT assumed to be income.
3. Known merchant: the category comes from the merchant's alias.
4. Otherwise the row goes to "Other", marked "needs review".

Users can fix any row. One fix can apply to every row from that merchant, and every change is logged. The optional
AI only fills in the step-4 rows, and its answer has to be in the allowed category list.

**11. Why exclude credit-card bill payments from spending?**
To avoid double counting. The purchases on the card are the spending, and the bill payment just settles them.
Internal transfers are excluded for the same reason: moving money between your own accounts isn't spending.

## SQL and analytics

**12. Walk me through one query.**
Use `sql/monthly_summary.sql`:
- A recursive CTE builds a calendar of months, so a month with no data shows as 0 instead of disappearing.
- Conditional aggregation computes expenditure, refunds, income and transfers in a single pass.
- `LAG()` gives the previous month for the month-over-month change.
- `NULLIF`/`CASE` avoids dividing by zero.

**13. How do you make sure a metric means the same thing on every page?**
Each metric is defined once, in SQL, and every page calls the same functions in `src/analytics.py`. A test checks
that the insight comparison equals the SQL monthly summary. Another test recomputes the totals independently with
pandas and compares them with the SQL results.

**14. How are filters applied safely?**
Every query has a `/*FILTERS*/` placeholder. It's replaced with a clause where the column names are fixed in code
and every value is a bound parameter. A test tries an injection string and checks that the table is still there.

**15. How does "spending increased because of X" work?**
`src/insights.py` compares the latest month with the previous one. If the latest month is partial, for example
data up to the 12th, it's compared with the 1st–12th of the previous month, so both windows have the same length.
The change is broken down by category: the category with the largest positive change is the main driver, and its
share of the total change is shown. If the previous period had zero spending, no percentage is shown.

## Pattern detection

**16. How did you detect subscriptions?**
The SQL uses `LAG(julianday(date))` to get the gap in days between payments to the same merchant. Python then
checks two things: do the gaps fit a schedule (monthly is 30 ± 5 days), and is the amount stable (within 10% of
the median for high confidence, 30% for possible)? Each subscription shows its reasoning. The user can confirm or
reject it, and the cost is labelled as an estimate.

**17. How did you detect anomalies? Why not machine learning?**
Each expense is compared with the user's *earlier* payments: the same merchant if it has 5 earlier payments,
otherwise the same category if it has 8. It's flagged when the robust z-score (median and MAD instead of mean and
standard deviation) is at least 3.5 **and** the amount is at least 2× the median. With too little history a payment
isn't checked at all. I evaluated it on labelled synthetic data against a threshold rule and two IQR variants, using
a temporal split. ML (Isolation Forest) wasn't justified: there's one feature per group, no real labels, and it
can't explain a flag. "Unusual" is never presented as fraud.

## Engineering

**18. What about privacy?**
- PDFs are processed in memory and never saved.
- Identifiers are masked before anything is stored.
- Logs contain only counts. pdfminer's debug logging is silenced because it can print page content, and a test
  caught this.
- Demo data and user data live in separate databases, with one-click delete.
- Public hosting gives each visitor a private in-memory database.
- The local SQLite file is documented honestly as unencrypted.

**19. How did you test it?**
There are 190+ pytest tests:
- hand-computed analytics on a 9-row fixture
- a 285-row synthetic dataset with ground-truth labels, where every row must be classified correctly
- synthetic PDFs built with reportlab: multi-page, wrapped lines, password-protected, scanned and corrupt files
- privacy tests: no file written, nothing sensitive in logs, AI off without a key
- API tests: the HTTP results equal the SQL layer, the import preview saves nothing before confirmation,
  merchant-wide edits need a matching confirmation count, and public sessions can't see each other's data

**20. What would you improve next?**
More bank parsers and OCR, learning rules automatically from manual corrections, budgets, and an encrypted local
database.

## Spendly 2.0 (web app + API)

**21. Why did you add FastAPI and Next.js instead of improving Streamlit?**
The Python logic in `src/` and `sql/` was already separate from the UI. A thin API could reuse it without
rewriting a single query or metric. Streamlit couldn't give me a custom app shell, drag-and-drop import, edit
dialogs or smooth motion, so the redesign needed a real front end. The Streamlit app still works on the same
code.

**22. How do you make sure the front end doesn't calculate different numbers?**
The front end never does money maths. It only formats paise into rupees. Every metric comes from the same SQL
files through `src/analytics.py`, and API tests check that the HTTP results equal the SQL layer.

**23. How does the import flow keep the "nothing saved before confirmation" rule?**
`POST /api/import/preview` parses the PDF in memory and keeps only the masked, extracted rows under a random
token. The token expires after 30 minutes. Only `POST /api/import/{token}/commit` writes to the database, in one
transaction.

**24. A user applies a category to "all transactions from this merchant". What stops it touching more rows than
they saw?**
The dialog shows the exact count and sends it as `expected_count`. The API recounts and refuses with HTTP 409 if
the numbers differ.

**25. What happens on a public deployment?**
Each browser session sends a random id. That session gets its own in-memory demo and user databases, which
expire after inactivity. Nothing is written to disk, and a test proves one session can't see another's data.

## Advanced SQL

**26. How do you make sure "expenditure" means the same thing in every query?**
It's defined once, in `src/metrics.py`, as `{{is_expense}}`, and every SQL file uses that placeholder. A test
fails if any file writes the rule by hand.

**27. How do you calculate a median in SQLite, which has no MEDIAN function?**
Number each merchant's payments with `ROW_NUMBER() OVER (PARTITION BY merchant ORDER BY amount)` and count them
with `COUNT() OVER (PARTITION BY merchant)`. Then take the middle row, or the average of the two middle rows when
the count is even (see `merchant_stats.sql`).

**28. A month shows ₹0. Is that real?**
Only if a statement covers it. `monthly_summary.sql` checks statement coverage with `EXISTS` and returns
`prev_status` (`none`, `not_covered`, `zero` or `value`), so a missing month never produces a fake −100% change.

**29. Why compare weekdays and weekends per day instead of by total?**
A month has about 22 weekdays and only 8 or 9 weekend days, so totals are always bigger on weekdays. A recursive
day calendar counts the actual days in the period, and spend per day is the fair comparison.

**30. What does the HHI tell you, and what are its limits?**
It's the sum of squared % shares: from near 0 (spread out) to 10,000 (one merchant). It's descriptive, one big
fixed cost like rent can dominate it, and it depends on how well merchant names were normalized.

## Budget Planner

**31. How is utilisation defined, and what happens with a ₹0 budget?**
Actual ÷ budget × 100, where actual uses the same `{{is_expense}}` rule as the rest of the app. With a ₹0
budget the percentage is undefined, so the SQL returns NULL (`CASE WHEN budget > 0`) instead of dividing by
zero. Any spending against a ₹0 budget still counts as over budget, and the rupee variance is shown.

**32. Why don't refunds reduce a category's spending?**
A refund lands in the Refunds category, and statements don't link it back to the original purchase. Guessing
the link would make category numbers unreliable, so refunds are shown separately with a net figure.

**33. How do you stop duplicate budgets?**
Validation in Python, backed by the database: a unique index on `(month, COALESCE(category, '*'))`. The
`COALESCE` matters because SQLite treats NULLs as distinct, so without it you could add two overall budgets.
The API turns the violation into a 409.

**34. What if the month isn't over yet?**
The month is marked partial and figures say "so far". A linear pace projection appears only if the data starts
on day 1 and covers at least 7 days, and it's labelled as an estimate. Partial months are left out of
month-on-month and repeated-overspend comparisons.

**35. How do you know the budget numbers match the rest of the app?**
A test checks that, for every demo month, each category's actual equals `category_spending` and the overall
equals `totals` for the same dates. Python rounds percentages half away from zero, like SQLite's `ROUND`,
because an early test caught 148.25 showing as 148.3 in SQL and 148.2 in Python.

## Data quality and anomaly evaluation

**36. Why not one overall data-quality score?**
Completeness, validity, uniqueness, balance consistency, categorisation and reconciliation have different
denominators (rows, complete rows, pairs, statements) and different fixes. An average would hide which one is
weak. Each is shown separately as numerator / denominator, and is "n/a" rather than 100% when nothing could be measured.

**37. Why is validity measured on complete rows only?**
So a row missing its date isn't counted as a failure twice, once for completeness and once for validity. That keeps
the dimensions independent, and the rejected-row counts add up to the total.

**38. What's the difference between parser accuracy and data quality?**
Parser accuracy compares what was extracted with what is printed (ground-truth fixtures, rows aligned in order).
Data quality asks whether the extracted data is complete and consistent. My synthetic fixtures score 100% on
parsing, which only shows the parsers handle the layouts they were built for. I don't claim real-world accuracy
until real statements are tested.

**39. What was wrong with the old anomaly detector?**
It computed quartiles over the whole filtered history, including later payments and the payment itself. So
March was judged with September's data, and the answer changed with the date filter. Now only earlier payments
are used. A test adds future payments and checks the verdict on an earlier one doesn't move.

**40. What did the evaluation show?**
On the held-out half: robust z had precision 0.79, recall 0.77 and F1 0.78, against 0.75 for both IQR versions
and 0.43 for a category-threshold rule. Over 5 other seeds it was 0.77 ± 0.03 vs 0.74. That's a small gain, about
one standard deviation. Tuning on the first half overfit and lowered test recall, so I kept the textbook defaults.
Known misses: unusually small payments. Known false alarms: genuine big purchases. That's why flags can be marked "expected".

**41. Why a robust z-score instead of a normal z-score?**
The mean and standard deviation are pulled by the very outliers you're looking for. The median and MAD aren't. When
MAD is 0 (e.g. identical subscription charges) it falls back to the mean absolute deviation. If every earlier
payment was identical, only the "≥ 2× median" rule decides.

## Numbers worth knowing (demo data)
- 285 synthetic rows, April–September 2026. One exact duplicate is skipped, so 284 are imported.
- The August spike comes from a ₹54,999 laptop. It's flagged as unusual at 29.8× the median of the 11 earlier Shopping
  payments (robust z 116). Amazon itself had too few earlier payments to be the yardstick.
- Demo data quality: completeness 100%, uniqueness 99.6% (1 verbatim copy of 285), balance consistency 100%,
  categorisation coverage 91.5% (260 of 284), reconciliation n/a (the demo CSV prints no opening/closing balance).
- 6 high-confidence recurring payments cost about ₹21,190 a month (estimated).
