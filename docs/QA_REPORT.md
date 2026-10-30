# Spendly end-to-end QA report

> Security items in this report were revisited in [SECURITY.md](SECURITY.md) (phase 1 hardening): rate limiting,
> log redaction, CSP and session handling have since been implemented.

Date: 29 Oct 2026 · Environment: Linux x86_64, Python 3.13.18, Node 22.23.4, Next.js 16.4.3, FastAPI 0.162,
Streamlit 1.66.1, Chromium (Playwright 1.63) · Data: synthetic only (no real statements, no credentials).

## Baseline (before any change, commit `1c41398`)

| Check | Command | Result |
|---|---|---|
| Python + API tests | `pytest` | 315 passed |
| Coverage | `pytest --cov=src --cov=api` | 88% (`src/ui.py`, `src/charts.py` are Streamlit-only: 0%) |
| Frontend lint / types / build | `npm run lint`, `npx tsc --noEmit`, `npm run build` | all clean |
| Browser E2E | none in the repo | NOT RUN (no suite existed) |

## Test matrix (final run)

| Component | Test type | Scenario | Expected | Actual | Status |
|---|---|---|---|---|---|
| Financial maths | known-answer | hand-calculated account, 4 months (21 tests) | totals, per-month, categories, MoM match hand values | match | PASS |
| Financial maths | invariants | shuffled row order (5 seeds), deterministic aggregates, invalid rows excluded | totals unchanged | unchanged | PASS |
| Import | duplicates | same file twice / overlapping statement with and without balances | blocked / skipped / flagged | as expected | PASS |
| PDF parsing | unit | empty, 1 row, 260 rows multi-page, punctuation, upper-case extension, corrupt, non-PDF, password wrong/missing | parsed or safe, specific error | as expected (after QA-1, QA-5) | PASS |
| Money / dates | unit | lakh grouping, 3-decimal amounts, exponent, leap days, year/month boundaries, ambiguous dates | exact paise; never guessed | as expected | PASS |
| Normalisation | unit | aliases, spelling/case/whitespace, distinct merchants, idempotence | merge only true aliases | as expected | PASS |
| API | integration | import preview → commit → re-import → delete; cancel; client-supplied totals ignored; malformed JSON/methods/ids; bulk edits; 9 concurrent threads | correct status codes, no partial writes | as expected (after QA-4) | PASS |
| Database | integrity | interrupted commit rollback, atomic bulk edit, constraints, migration of old DB | no partial data | as expected | PASS |
| Isolation | integration | demo vs My data, public sessions, foreign ids, delete/reset | no cross-over | none | PASS |
| Privacy | integration | logs during import, masking in DB and CSV, no PDF on disk, CSV formula cells | no leaks | as expected (after QA-3) | PASS |
| Browser E2E | Playwright (70 checks) | journeys A–G, responsive, a11y | all checks | 70 / 70 | PASS |
| Streamlit | browser | 6 pages render; synthetic PDF → preview → import → DB | 8 rows, ₹5,528.50 | as expected | PASS |
| Dependencies | audit | `pip-audit -r requirements-api.txt`, `npm audit` | — | 0 known vulnerabilities each | PASS |
| Performance | benchmark | 100 / 1,000 / 10,000 transactions | measured | see below | PASS (measured) |
| Gemini AI | live service | real API call | — | no key in the test environment; mocked in unit tests | BLOCKED |
| Real bank PDFs | parser accuracy | real statements | — | none available (by policy) | BLOCKED |
| Screen reader | manual | NVDA / VoiceOver | — | not available in this environment | NOT RUN |

## Defects found and fixed

| ID | Sev. | Defect | Root cause | Fix (files) | Regression test |
|---|---|---|---|---|---|
| QA-3 | P2 | CSV export wrote statement text starting with `=`, `+`, `-`, `@` verbatim (spreadsheet formula injection) | export copied text columns unchanged | prefix `'` on risky text cells; numbers untouched (`api/main.py`) | `test_qa3_csv_export_neutralises_formulas` |
| QA-4 | P2 | "Apply to every transaction from this merchant" could leave some rows changed if a write failed half-way | each row was its own DB transaction | the whole bulk edit runs in one transaction; `database.transaction` is now re-entrant (`api/main.py`, `src/database.py`) | `test_qa4_bulk_category_change_is_atomic` |
| QA-1 | P3 | A supported statement with no rows said "layout not supported" | the parser loop treated "no rows" like "not recognised" | new `EmptyStatementError` with a specific message (`src/pdf_parser.py`) | `test_qa1_empty_supported_statement_says_so` |
| QA-2 | P3 | A one-row statement with a balance was reported as "no balance column" (warning + quality finding) | the warning used "no pair checked" as a proxy for "no balance" | distinguish "no balance at all" from "fewer than two rows" (`src/data_validator.py`, `src/quality.py`) | `test_qa2_single_row_…` |
| QA-5 | P3 | A wrong PDF password got the same message as a missing one | the password case wasn't distinguished | "That password didn't open the PDF" when one was given (`src/pdf_parser.py`) | `test_qa5_wrong_password_message` |
| QA-6 | P3 | Horizontal page overflow at 768 px on Transactions | `sr-only` text inside a scrollable table escaped its container (no positioned ancestor) | `relative` on the scroll containers (transactions, analysis, quality, anomalies, chart tables) | E2E "no horizontal overflow at 768×1024" |
| QA-7 | P3 | Tertiary text (`--color-faint` #5f675d) had a 3.0–3.4:1 contrast ratio, below WCAG AA 4.5:1 | design token too dark | #828a80 (≥ 4.9:1 on every surface), also in chart axes | E2E "text colour tokens meet WCAG AA" |
| QA-8 | P3 (perf) | Overview took ~3.0 s at 10,000 transactions | anomaly statistics (quartiles, MAD) computed for every payment; median computed 3× | skip the costly statistics when the ratio rule already fails; cache the median. Same flags (the committed evaluation JSON still matches) | `test_committed_results_match_a_fresh_run` + all anomaly tests |

Each regression test was confirmed to **fail on the baseline commit** (QA-1 … QA-5) and pass after the fix.
Hardening, not a confirmed defect: the "Skip to content" link now targets the *visible* `<main>`. Next.js keeps the
previous route mounted, hidden, so two elements share `id="main"` after client-side navigation.

## Financial correctness (known-answer account)

Rules: README "Financial metric definitions". Expected values were calculated by hand (`tests/test_qa_known_answer.py`).

| Scenario | Expected | Actual |
|---|---|---|
| Total expenditure / income / refunds / net cash flow | ₹96,837 / ₹1,50,000 / ₹500 / +₹51,663 | match |
| January (salary, rent, food, travel, shopping, refund, own transfer, card bill, friend's transfer, duplicate pair, unknown shop) | exp ₹19,639 · inc ₹50,000 · net +₹28,861 | match |
| February with a ₹60,000 purchase | exp ₹76,249 · net −₹26,249 (negative shown as negative) | match |
| March: covered, no activity | ₹0, `is_covered = 1`, MoM −100% | match |
| April 1–10 partial vs March 1–10 with ₹0 | "isn't meaningful", no percentage | match |
| Own transfer / card bill | excluded from expenditure; card bill counted in cash flow | match |
| Friend's transfer | type "other", not income; UPI ID masked | match |
| Refund | own category, not income, not netted against Shopping | match |
| Categories | Shopping 62,000 · Rent 30,000 · Subscriptions 1,947 · Food 1,300 · Travel 1,200 · Other 390 | match |
| Average month | (19,639 + 76,249 + 0) / 3 complete months | match |
| Recurring (Netflix with a missing month; rent ×2) | not claimed as confident subscriptions | match (conservative) |
| ₹60,000 purchase with too little history | not flagged; counted as "not checked" | match |
| Same rows in a new file with balances | 4 exact duplicates skipped, totals not doubled | match |
| Same rows without balances or IDs | imported, every one flagged "possible duplicate" | match (documented rule) |

## Security and privacy

Confirmed and fixed: QA-3 (CSV formula injection), QA-4 (non-atomic bulk edit).
Verified by tests:
- the upload checks (extension, signature, size → 413, page limit, corrupt and encrypted files);
- no PDF written to disk, and no statement content in the API or Streamlit logs;
- parameterised SQL with whitelisted identifiers;
- demo / My data / public-session isolation, including foreign IDs;
- delete and reset scope, and generic 500 responses with no stack traces.

`pip-audit` and `npm audit` reported no known vulnerabilities.

Unresolved risks (documented, not fixed because they need architecture or host configuration):
- No authentication and no rate limiting. In public mode, the session ID is the only key.
- The local SQLite database is unencrypted.
- There is no Content-Security-Policy.
- Uvicorn's access log records query strings, which can include merchant filter values (42 such lines in the E2E log). Run with `--no-access-log` on shared hosts.
- Public mode needs a single worker.

This is a code review plus automated tests, not a penetration test.

## Performance (`python -m scripts.benchmark`, server side, in-memory DB)

| Operation (ms) | 100 txns | 1,000 txns | 10,000 txns |
|---|---|---|---|
| PDF preview | 483 | 5,125 | n/a (exceeds the 60-page limit) |
| CSV preview | 8 | 138 | 1,259 |
| Commit | 2 | 21 | 185 |
| Overview | 143 | 197 | 1,042 (was ~3,007 before QA-8) |
| Filtered overview | 77 | 140 | 771 |
| Insights | 91 | 133 | 956 |
| Transactions page (50 rows) | 17 | 14 | 18 |
| CSV export | 23 | 26 | 255 |
| Monthly PDF report | 289 | 306 | 984 |

PDF parsing (pdfplumber) dominates imports: about 5 s for a 1,000-row statement. That is acceptable for a one-off
import, but it's the first thing to optimise if larger statements matter.

## Commands executed (final run)

| Command | Outcome |
|---|---|
| `pytest` (with `--cov=src --cov=api`) | 395 passed, 0 failed; coverage 89% |
| `ruff check <new files> --select F` | clean (3 older unused-import warnings in untouched tests and 10 in `scripts/generate_sample_data.py` remain) |
| `npm run lint` / `npx tsc --noEmit` / `npm run build` | exit 0 / 0 / 0 |
| `python -m e2e.run_e2e … --streamlit …` | 70 passed, 0 failed (225 s) |
| `python -m scripts.benchmark` | table above |
| `pip-audit -r requirements-api.txt` / `npm audit` | 0 known vulnerabilities |

## Remaining issues and manual checks

- **Blocked:** a live Gemini call (no key; tested with mocks) and real bank statements (none used, by policy).
- **Not run:** screen-reader testing; Safari/Firefox (Chromium only); real touch devices (viewport emulation only).
- **Limitations:** only two statement layouts are supported, and there's no OCR for scanned PDFs. Plus the security limits listed above.
- 96 `ResourceWarning`s in pytest come from test fixtures that don't close in-memory databases. Test hygiene, not an app defect.

## Verdict: PASS WITH LIMITATIONS

All automated suites pass: 395 Python/API tests, 70 browser checks, Streamlit included. The import-to-dashboard
journey matches hand-calculated values, and two P2 and six P3 defects were fixed with regression tests. No known
release-blocking defect remains. Limitations: no authentication or rate limiting, synthetic-only parser evidence,
a blocked live AI test, and no screen-reader or cross-browser testing.

---

## Update: manual testing and portfolio polish, 29–31 Oct 2026

The sections above are the original 29 Oct record and are unchanged. This section adds the hands-on test that
followed: six synthetic statements imported on a Windows laptop through the web app and Streamlit, plus a phone
layout check. Every checked figure matched the source statements. Twenty defects were found and fixed, each in
a commit on `main`.

| # | Found during manual testing | Fixed in |
|---|---|---|
| 1 | "1 transactions" and similar plural wording | `8b19276`, `b35b95b` |
| 2 | A finding with 0 rows still flagged kept its Warning badge | `8b19276` |
| 3 | Cash-flow tiles didn't visibly add up (credit-card bill) | `b35b95b` |
| 4 | Category fixes weren't reused on later imports (now rules per merchant and direction) | `4590c42` |
| 5 | Overview net-cash-flow note didn't mention excluded own transfers | `4590c42` |
| 6 | Uncategorised count included skipped exact duplicates | `4590c42` |
| 7 | Balance-mismatch rows missing from Needs review | `4590c42` |
| 8 | A month with no statement drawn as ₹0 and called "no expenditure" | `8868e67` |
| 9 | Transactions header totals looked inconsistent with Overview | `6c2e21a` |
| 10 | Badge 29% vs sentence 28% for the same 28.5% | `e8a379a` |
| 11 | "+nan%" in the PDF report for a change from ₹0 | `ef03e49` |
| 12 | Unusual payments compared with the "Other" catch-all category | `ef03e49` |
| 13 | Landing page's second button scrolled instead of opening the user's data | `50170af`, `77bf4d0` |
| 14 | Landing page wider than a phone screen; menu button off-screen | `14bfa31` |
| 15 | Import & Settings 1 px too wide on phones | `14bfa31` |
| 16 | Streamlit used the old logo | `7180515` |
| 17 | Streamlit kept the demo's date range in My data | `7180515` |
| 18 | Streamlit compared half-months where the web app compared full months | `7180515` |
| 19 | Streamlit used a light theme | `3415e8a` |
| 20 | Two different taglines | `3415e8a` |

Portfolio polish (31 Oct): README rewritten and shortened (the full previous README is now
[TECHNICAL_GUIDE.md](TECHNICAL_GUIDE.md)); [SQL_SHOWCASE.md](SQL_SHOWCASE.md) added; screenshots recaptured
from the current app; monthly charts drawn with straight segments instead of smoothed curves; the "why spending
changed" recurring line now says it is the amount actually paid (the KPI tile is an estimate); the default Gemini
model changed from `gemini-2.5-flash` (Google now limits access for new users) to `gemini-3.6-flash`; 11 tests
added for Gemini failure paths (timeouts, 429, rejected key, server error, malformed replies, what is sent).

### Results, 31 Oct 2026

| Check | Result |
|---|---|
| `pytest` (no Gemini key in the environment) | 456 passed, 0 failed |
| `npm run lint` / `npx tsc --noEmit` / `npm run build` | clean / clean / compiled |
| Browser E2E, web app + Streamlit (`python -m e2e.run_e2e --streamlit …`) | 69 passed, 0 failed |
| Browser E2E, public-deployment journey (`--public`) | 7 passed, 0 failed |
| Horizontal overflow at 393 / 375 / 320 px, 9 pages | none (checked 30 Oct) |
| `pip-audit -r requirements-api.txt` / `npm audit --omit=dev` | 0 known vulnerabilities |
| README links and images | all resolve to files in the repo |

Not run: a live Gemini request (no key; covered by mocked tests), real bank statements (synthetic data only, by
design), Safari and Firefox, screen readers.

Verdict: **PASS WITH LIMITATIONS.** The limitations are unchanged: two supported statement layouts, no OCR,
synthetic-only evidence, single-user local storage without encryption, and in-memory per-session data on a
public deployment.
