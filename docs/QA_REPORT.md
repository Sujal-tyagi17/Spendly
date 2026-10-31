# Spendly QA report

Last updated 31 Oct 2026. This is the engineering record of what was tested, what passed, what was fixed and what
was not tested. Results marked **historical** were reported on an earlier date and are kept as they were reported;
everything under "Latest automated results" was re-run on 31 Oct 2026 against commit `276c853`.

## 1. Executive summary

- **Scope.** Automated unit, integration and known-answer tests of the Python/SQL core and API; browser end-to-end
  tests of the Next.js dashboard and the Streamlit app; a manual test with six synthetic statements on Windows; a
  smoke check of the Render deployment. All data was synthetic.
- **Latest results (31 Oct 2026).** 456 Python tests passed (coverage 90%). 70 browser checks passed, plus 7 in the
  public-deployment journey. Lint, type check and production build were clean. `pip-audit` and the production-only
  `npm audit` found no known vulnerabilities; the full `npm audit` reports 16 moderate findings in development-only
  ESLint packages (section 7).
- **Defects.** 8 found in the original QA pass (29 Oct) and 20 in manual testing (29–31 Oct). All 28 are fixed.
- **Main limits.** Two statement layouts, no OCR, no real statements tested, no live Gemini request, Chromium only,
  no screen-reader testing. Single-user local storage is unencrypted and there is no authentication.

**Verdict: PASS WITH LIMITATIONS** (section 10).

## 2. Test environment

| Item | Value |
|---|---|
| Automated runs | Linux x86_64, Python 3.13.18, Node 22.23.4 |
| Frameworks | Next.js 16.4.3, FastAPI, Streamlit 1.66.1 |
| Browser | Chromium via Playwright (desktop and phone viewports emulated) |
| Manual testing | Windows laptop, Chrome, PowerShell; same code from GitHub |
| Data | Synthetic only: the built-in demo dataset and generated statement PDFs. No real statements, no API keys |

## 3. Latest automated results (re-run 31 Oct 2026)

### Passed

| Check | Command | Result |
|---|---|---|
| Python unit, integration and known-answer tests | `pytest --cov=src --cov=api` (no Gemini key set) | 456 passed, 0 failed; coverage 90% |
| Browser E2E, dashboard + Streamlit (journeys A–G, responsive, accessibility) | `python -m e2e.run_e2e --api-log … --streamlit … --streamlit-db …` | 70 passed, 0 failed |
| Browser E2E, public deployment (sessions, isolation, rate limit) | `python -m e2e.run_e2e --public` against an API with `SPENDLY_PUBLIC_DEPLOYMENT=true` | 7 passed, 0 failed |
| Frontend lint / type check / production build | `npm run lint`, `npx tsc --noEmit`, `npm run build` | clean / clean / compiled |
| Python dependency audit | `pip-audit -r requirements-api.txt` | no known vulnerabilities |
| Production JavaScript dependency audit | `npm audit --omit=dev` | 0 vulnerabilities |
| Performance benchmark | `python -m scripts.benchmark` | measured; see section 8 |

### Findings from checks that ran (not passes)

| Check | Result | Status |
|---|---|---|
| Full JavaScript dependency audit | `npm audit`: 16 moderate, all in the ESLint toolchain (`minimatch` denial-of-service advisory). Not part of the built site; `npm audit --omit=dev` is clean. The suggested fix installs a breaking ESLint version. | Open, development-only |
| Python lint (`ruff check src api tests scripts --select F`) | 12 warnings: unused f-string prefixes in `scripts/generate_sample_data.py` (9) and `tests/test_pdf_parser.py` (1), unused imports in `tests/test_api.py` (2). None in `src/` or `api/`. | Open, cosmetic |
| pytest warnings | 96 `ResourceWarning`s from test fixtures that don't close in-memory databases | Open, test hygiene |

### Test-count history

The counts grew as tests were added; none were removed.

| Stage | Commit | Python tests | Browser checks |
|---|---|---:|---:|
| Baseline before QA (historical) | `1c41398` | 315 passed | none existed |
| Original QA final run, 29 Oct (historical) | `11e1fac` | 395 passed | 70 passed (with Streamlit) |
| End of manual testing, 30 Oct (re-run 31 Oct to confirm) | `89a0686` | 445 passed | — |
| After 11 Gemini failure-path tests, 31 Oct (current) | `276c853` | 456 passed | 70 passed, plus 7 public |

**Browser count, 70 vs 69.** Earlier 30–31 Oct runs reported 69. The check "API log has no statement content"
only runs when `--api-log` is given, and those runs omitted it. Re-run on 31 Oct with `--api-log`: 70 passed. Journeys
A–G are unchanged since `11e1fac`; the later edit (`f212427`) added the separate `--public` journey.

## 4. Manual end-to-end testing (29–31 Oct 2026)

Six synthetic statements were imported through both interfaces on Windows. Every figure checked was compared with
values computed independently from the generated data. This shows that the pipeline handles these layouts and edge
cases; it does not measure accuracy on real bank statements.

| Statement | What it validates | Observed |
|---|---|---|
| 1. October bank statement (clean) | Baseline parsing, reconciliation | 17 rows; 0 balance mismatches in 16 pairs; reconciles; 1 uncategorised |
| 2. November bank statement (3 pages) | Multi-page parsing, volume | 131 rows; 0 mismatches in 130 pairs; November expenditure ₹1,59,415 |
| 3. PhonePe UPI statement | Second layout, no balance column, near-duplicates | 34 rows; 1 possible duplicate flagged; "No running balance" info finding |
| 4. December bank statement (messy) | Wrapped line, missing amount, repeated row, misprinted balance | 11 found, 1 rejected, 1 exact duplicate skipped, 2 of 8 pairs mismatched; still reconciles ₹11,050.50 → ₹71,804.50 |
| 5. October–November overlap | Re-imported rows | 61 exact duplicates; 0 imported; totals unchanged |
| 6. January bank statement, password-protected | Encrypted PDF | Missing and wrong passwords refused with distinct messages; correct password opens 15 rows; reconciles |

With statements 1, 2 and 4 loaded, the exported CSV (157 rows) matched the dashboard: expenditure ₹2,11,344.50,
all credits ₹2,57,299, 24 rows needing review. Phone layouts were checked at 393, 375 and 320 px on 9 pages with no
horizontal overflow (30 Oct).

**Deployment smoke check (31 Oct).** On `spendly-insights.onrender.com`: `/api/health` returned
`{"ok":true,"public":true}`; a request without a session was refused; the demo loaded 284 transactions and ₹3,25,627
expenditure; statement 1 imported (17 rows); an incognito window's My data was empty. The browser part was done by
hand. The automated browser suite was not run against the live site.

## 5. Financial correctness (known-answer account)

Expected values were calculated by hand for a four-month account (`tests/test_qa_known_answer.py`, 21 tests,
part of the current 456). Metric definitions: [TECHNICAL_GUIDE.md](TECHNICAL_GUIDE.md), "Financial metric
definitions".

| Scenario | Expected (hand-calculated) | Result |
|---|---|---|
| Totals: expenditure / income / refunds / net cash flow | ₹96,837 / ₹1,50,000 / ₹500 / +₹51,663 | match |
| January: salary, rent, food, travel, shopping, refund, own transfer, card bill, friend's transfer, duplicate pair, unknown shop | expenditure ₹19,639 · income ₹50,000 · net +₹28,861 | match |
| February with a ₹60,000 purchase | expenditure ₹76,249 · net −₹26,249 | match |
| March: covered by a statement, no activity | ₹0, covered, month-over-month −100% | match |
| April 1–10 (partial) vs March 1–10 with ₹0 | no percentage; "isn't meaningful" | match |
| Own transfer and card bill | excluded from expenditure; the card bill counts in net cash flow | match |
| Friend's transfer | type "other", not income; UPI ID masked | match |
| Refund | own category; not income; not netted against Shopping | match |
| Category totals | Shopping 62,000 · Rent 30,000 · Subscriptions 1,947 · Food 1,300 · Travel 1,200 · Other 390 | match |
| Average month | (19,639 + 76,249 + 0) ÷ 3 complete months | match |
| Recurring (Netflix with a missing month; rent twice) | not claimed as confident subscriptions | match |
| ₹60,000 purchase with too little history | not flagged as unusual; reported as "not checked" | match |
| Same rows in a new file, with balances | 4 exact duplicates skipped; totals not doubled | match |
| Same rows without balances or IDs | imported and flagged "possible duplicate" | match |

## 6. Defects found and fixed

### Original QA pass (29 Oct 2026)

Regression tests for QA-1 to QA-5 were confirmed to fail on the baseline commit and pass after the fix (historical).

| ID | Sev. | Defect | Root cause | Fix | Verification |
|---|---|---|---|---|---|
| QA-3 | P2 | CSV export wrote text starting with `=`, `+`, `-`, `@` verbatim (formula injection) | text columns copied unchanged | prefix `'` on risky text cells | `test_qa3_csv_export_neutralises_formulas` |
| QA-4 | P2 | A merchant-wide category change could leave rows half-updated if a write failed | each row was its own DB transaction | one transaction for the whole edit; re-entrant `database.transaction` | `test_qa4_bulk_category_change_is_atomic` |
| QA-1 | P3 | An empty supported statement said "layout not supported" | "no rows" treated as "not recognised" | `EmptyStatementError` with its own message | `test_qa1_empty_supported_statement_says_so` |
| QA-2 | P3 | A one-row statement with a balance was reported as having no balance column | "no pair checked" used as a proxy | distinguish no balance from fewer than two rows | `test_qa2_single_row_…` |
| QA-5 | P3 | A wrong PDF password got the same message as a missing one | case not distinguished | separate message for a wrong password | `test_qa5_wrong_password_message` |
| QA-6 | P3 | Page overflowed horizontally at 768 px on Transactions | screen-reader text escaped a scroll container | `relative` on scroll containers | E2E "no horizontal overflow" |
| QA-7 | P3 | Tertiary text contrast 3.0–3.4:1, below WCAG AA | colour token too dark | `#828a80` (≥ 4.9:1 on every surface) | E2E "text colour tokens meet WCAG AA" |
| QA-8 | P3 | Overview took ~3.0 s at 10,000 transactions | anomaly statistics computed for every payment; median computed 3 times | skip statistics when the ratio rule fails; cache the median | `test_committed_results_match_a_fresh_run` and the anomaly tests |

### Manual testing (29–31 Oct 2026)

Found by hand; each fix is in the named commit. "Test" names a test added with the fix; "checked" means it was
verified in the browser and covered only by the existing suites.

| # | Defect | Fix | Commit | Verification |
|---|---|---|---|---|
| 1 | "1 transactions" and similar plural wording | shared plural helper (Python and TypeScript) | `8b19276`, `b35b95b` | test: `tests/test_text.py` |
| 2 | A finding with 0 rows still flagged kept its Warning badge | Resolved badge | `8b19276` | checked |
| 3 | Cash-flow tiles didn't visibly add up (card bill) | reconciling line under the tiles | `b35b95b` | checked |
| 4 | Category fixes weren't reused on later imports | rules per merchant and direction, applied on import | `4590c42` | tests: `tests/test_merchant_rules.py` |
| 5 | Net-cash-flow note didn't mention excluded own transfers | reworded | `4590c42` | checked |
| 6 | Uncategorised count included skipped exact duplicates | counts only imported rows | `4590c42` | test: `test_uncategorised_count_ignores_skipped_exact_duplicates` |
| 7 | Balance-mismatch rows missing from Needs review | flagged with a reason; old data migrated once | `4590c42` | tests: `test_balance_mismatch_rows_are_put_under_needs_review` and the migration test |
| 8 | A month with no statement drawn as ₹0 and called "no expenditure" | gaps shown as gaps; comparison names the missing month | `8868e67` | test: `test_a_gap_between_statements_is_not_compared_as_zero` |
| 9 | Transactions header totals looked inconsistent with Overview | labelled "all debits / all credits" with an explanation | `6c2e21a` | checked |
| 10 | Badge 29% vs sentence 28% for 28.5% | same half-up rounding | `e8a379a` | test: `test_whole_pct_rounds_halves_up_like_the_web_app` |
| 11 | "+nan%" in the PDF report for a change from ₹0 | shows "new" | `ef03e49` | checked (PDF text) |
| 12 | Unusual payments compared with the "Other" catch-all category | uncategorised rows use only their merchant's history | `ef03e49` | test: `test_uncategorised_other_is_not_a_comparison_group` |
| 13 | Landing page's second button scrolled instead of opening the user's data | "Use your own statement" opens My data | `50170af`, `77bf4d0` | checked |
| 14 | Landing page wider than a phone; menu button off-screen | conflicting display classes fixed | `14bfa31` | checked: no overflow at 393/375/320 px |
| 15 | Import & Settings 1 px too wide on phones | label kept inside its scroll area | `14bfa31` | checked: same |
| 16 | Streamlit used the old logo | same mark as the dashboard | `7180515` | checked |
| 17 | Streamlit kept the demo's date range in My data | filters kept per data source | `7180515` | checked; E2E Streamlit journey |
| 18 | Streamlit compared half-months (−67.2%) where the dashboard showed −84.8% | untouched date range means "all dates" | `7180515` | checked |
| 19 | Streamlit used a light theme | dashboard's dark theme and font | `3415e8a` | checked |
| 20 | Two different taglines | one tagline everywhere | `3415e8a` | checked |

## 7. Security and privacy

**Original QA findings (29 Oct, historical).** QA-3 and QA-4 above. Also reported as unresolved at the time: no
authentication, no rate limiting, no Content-Security-Policy, access logs recording query strings, unencrypted
SQLite, single worker needed for public mode.

**Changes since (security hardening, `f212427`).** Server-issued session tokens; in-process rate limits (429 with
`Retry-After`); query strings redacted from access logs; CSP on the dashboard and API; database files `0600`;
JSON body limit; upload size checked before the body is read. Details and evidence: [SECURITY.md](SECURITY.md).

**Verified in the current run.** Tests in `tests/test_security.py` and `tests/test_privacy.py` (part of the 456):
session forgery and expiry, cross-session isolation, rate limits, upload and body limits, log redaction with a real
uvicorn process, file permissions, no statement content in logs, masking in the database and CSV. The public
journey (7/7) checks isolation and rate limiting in a browser. Gemini failure paths (`tests/test_ai_failures.py`):
timeouts, rate limits, rejected key, server errors and malformed replies give friendly errors; only sanitised merchant
labels are sent; the key is sent in a header and never logged.

**Remaining limitations.**
- No authentication. In public mode a session token is the only key, and data lives in memory for that session.
- Local SQLite files are not encrypted (access-restricted on POSIX only).
- Rate limits are per process: one worker and one instance are required.
- The CSP allows inline scripts (`'unsafe-inline'`), needed by statically rendered Next.js pages.
- In the single-container Render deployment all visitors reach the API through the built-in proxy, so the per-IP
  limit on new sessions (10 a minute) is shared by all visitors.
- The full `npm audit` reports 16 moderate findings in development-only ESLint packages (section 3).

This is a code review plus automated tests and dependency audits, not a penetration test.

## 8. Performance

`python -m scripts.benchmark`, server-side, in-memory database, on the Linux test machine (31 Oct). Times vary by
machine. The full table is in [TECHNICAL_GUIDE.md](TECHNICAL_GUIDE.md#performance).

| Operation (ms) | 100 txns | 1,000 txns | 10,000 txns |
|---|---:|---:|---:|
| PDF preview | 429 | 3,868 | n/a (page limit) |
| Overview | 98 | 124 | 649 |
| Insights | 56 | 109 | 616 |
| Monthly PDF report | 197 | 186 | 664 |

PDF parsing dominates imports (about 4 seconds for a 1,000-row statement). Overview at 10,000 transactions took
~3.0 s before QA-8 and 1.0 s after it on 29 Oct (historical, same machine type); 0.65 s in this run.

## 9. Not tested and known limitations

**Not run** (never attempted in any run):
- Safari and Firefox (Chromium only).
- Screen-reader testing (NVDA, VoiceOver).
- Physical phones and tablets (viewport emulation and a desktop browser's device mode only).
- The automated browser suite against the live Render deployment (checked by hand instead).

**Blocked** (attempted or required, but a dependency was unavailable):
- A live Gemini request: no API key in the test environment. Covered by mocked tests only.
- Parser accuracy on real bank statements: no consented real statements were available. Parser evaluation used
  synthetic fixtures ([PARSER_EVALUATION.md](PARSER_EVALUATION.md)).

**Known limitations of the software** (not test gaps):
- Two statement layouts: a bank table (Date, Description, Debit, Credit, Balance) and a PhonePe-style UPI statement.
- No OCR; scanned PDFs are rejected with a message.
- Recurring payments need at least three payments; unusual-payment detection was evaluated on synthetic labels only
  ([ANOMALY_EVALUATION.md](ANOMALY_EVALUATION.md)).
- Single-user local app; see section 7 for the security limits.

## 10. Verdict: PASS WITH LIMITATIONS

On 31 Oct 2026, 456 Python tests, 70 browser checks and the 7-check public journey passed with no failures, and the
build, type check and lint were clean. Manual testing with six synthetic statements matched every checked figure,
and all 28 defects found across both passes are fixed. Open items: development-only `npm audit` findings, minor lint
warnings in scripts and tests, and the untested areas in section 9. The evidence is synthetic and Chromium-only, so
it supports a portfolio demo, not a claim of accuracy on real statements or readiness for real users' data.
