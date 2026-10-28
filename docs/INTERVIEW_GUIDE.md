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
I used Tukey's rule: a payment is flagged when it's above Q3 + 1.5×IQR **and** at least 2× the median of
similar payments. "Similar" means the same merchant if it has enough history, otherwise the same category. It's
explainable, it works on small data, and it doesn't need training data that a single user doesn't have. Groups
with fewer than 8 payments are skipped. "Unusual" is never presented as fraud.

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

## Numbers worth knowing (demo data)
- 285 synthetic rows, April–September 2026. One exact duplicate is skipped, so 284 are imported.
- The August spike comes from a ₹54,999 laptop. It's flagged as unusual at 28× the usual Amazon payment.
- 6 high-confidence recurring payments cost about ₹21,190 a month (estimated).
