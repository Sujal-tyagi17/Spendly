# Spendly security review: phase 1 (hardening, access model, privacy)

Date: 29 Oct 2026 · Baseline commit `11e1fac` · Scope: FastAPI API (`api/`), Python core (`src/`), Next.js app
(`web/`), Streamlit app (`app.py`). Synthetic data only. This is a code review plus automated tests,
**not a professional penetration test**.

## 1. Architecture map (as built)

| Question | Answer |
|---|---|
| How is a browser session created? | **Local mode:** none; there's one user per machine. **Public mode:** the browser calls `POST /api/session` on first use (or after a 401), and the server returns `secrets.token_urlsafe(32)` (256 bits). *Before this phase, the browser generated its own UUID and the server accepted any well-formed value.* |
| How is it sent? | `X-Spendly-Session` header on every API call, via the same-origin `/api/*` proxy. It is never put in a URL, never in a cookie, and isn't logged. |
| Where is it stored? | Browser: `sessionStorage` (this tab only). Server: `ConnectionManager._issued` (process memory: token → last use). |
| How are transactions tied to an owner? | By **which database** a request reaches: `(mode, session)` → a SQLite connection. Local: `data/spendly_demo.db` / `data/spendly_user.db`. Public: two in-memory databases per session. There are no owner columns. Every query runs on the connection chosen in the `ctx` dependency, so a transaction ID is only meaningful inside its own database. |
| Demo vs personal data | Separate databases chosen by `X-Spendly-Mode` (validated: `demo` / `user`). Imports are allowed only in `user`; "delete all" only in `user`; reset only in `demo`. |
| Can session IDs be guessed, forged or reused? | Guessing: 256 bits, not feasible. Forging: tokens the server didn't issue get 401. Reuse: a token works until 2 h idle, `DELETE /api/session`, or a process restart. It is a **bearer secret**: anyone holding it (e.g. via XSS or a shared screen) has that session. |
| How are requests authorised? | `ctx()` validates the mode and the session (public), then picks the connection. Import previews are stored with `(owner, mode)` and checked on read, commit and discard. There are no per-user permissions, because there are no users. |
| Scope of exports, deletes, reports | Always the connection from `ctx()`: CSV export, PDF report, "delete all" (user DB of that session only), demo reset (demo DB of that session only), `DELETE /api/session` (both DBs of that session). |
| Multiple workers? | **Not supported in public mode.** Sessions, previews and rate-limit counters are process-local, so a second worker or instance rejects the first one's tokens (tested: `test_state_is_process_local`). In local mode the SQLite files are shared, but pending imports are not, so use one worker there too. |
| Any endpoint bypassing the ownership checks? | None found. `/api/health`, `/api/session` (POST) and `/api/anomalies/evaluation` (static synthetic results) read no user data. |

Streamlit uses the same `src/` code. Locally it uses the same SQLite files (now `0600`). In public mode it keeps
per-Streamlit-session in-memory databases. It has no API surface of its own.

## 2. Findings

| ID | Finding | Severity | Status | Evidence |
|---|---|---|---|---|
| S1 | Local mode served "My data" to **any** client that could reach the API. If it was exposed by mistake (`--host 0.0.0.0` without public mode), every visitor shared one dataset and could read, export or delete others' statements. | P1 | **MITIGATED** (local mode refuses non-loopback peers and requests relayed for a non-local host; opt out with `SPENDLY_ALLOW_REMOTE`) | `test_local_mode_refuses_remote_peers`, `…relayed_for_a_public_host` |
| S2 | Uploads > 1 MB were written to a temporary file on disk (Starlette's spool threshold), contradicting "never stored". Oversized uploads (e.g. 30 MB) were fully received and spooled **before** the size check. | P1 | **FIXED AND VERIFIED** (Content-Length checked before the body is read → 413; spool threshold above the upload limit) | reproduced with a spy on `SpooledTemporaryFile`; `test_large_valid_upload_stays_in_memory`, `test_oversized_upload_rejected_before_the_body_is_read` |
| S3 | Public sessions were client-chosen, auto-created, unrevocable, and evicted least-recently-used, so opening many sessions could wipe other visitors' sessions. One visitor could also evict others' pending imports (global cap of 100). | P2 | **FIXED AND VERIFIED** (server-issued tokens, 401 for unknown/expired/ended, `DELETE /api/session`, active sessions are never evicted (503 when full), at most 3 pending previews per session) | `test_missing_forged_or_malformed_sessions_are_rejected`, `test_expired_session…`, `test_ended_session…`, `test_capacity_never_evicts_active_sessions`, `test_one_visitor_cannot_crowd_out_other_previews` |
| S4 | No rate limiting on PDF parsing, reports, exports, bulk edits, destructive actions or session creation. | P2 | **MITIGATED** (in-process sliding-window limits, on by default in public mode; 429 + `Retry-After`) | `test_rate_limits_per_session_with_retry_after`, `test_session_creation_is_rate_limited`, `test_global_session_cap_survives_ip_spoofing`, browser journey P |
| S5 | Uvicorn access logs recorded query strings, e.g. `merchants=…` and `search=…` (42 such lines in the QA run). | P2 | **FIXED AND VERIFIED** (logging filter → `?[redacted]`; installed when the app is imported) | `test_real_uvicorn_logs_contain_no_filters_or_session_tokens` (real uvicorn process); E2E log: 0 filter values, 33 redacted lines |
| S6 | No Content-Security-Policy. | P2 | **FIXED AND VERIFIED** (web: same-origin policy built from actual resources; API: `default-src 'none'`) | headers checked; 70/70 browser checks pass with the CSP and no console violations |
| S7 | SQLite files created `0644` (readable by every user on the machine). | P2 | **FIXED AND VERIFIED** (`0600` on create/open, POSIX) | `test_database_files_are_private`; E2E data folders show `600` |
| S8 | JSON request bodies had no size cap. | P3 | **FIXED AND VERIFIED** (64 KB; `Transfer-Encoding` without length → 411) | `test_json_body_limit_and_length_checks` |
| S9 | Discarding someone else's (or an unknown) import preview returned `200 ok` (no effect, but misleading). | P3 | **FIXED AND VERIFIED** (404) | `test_cross_session_isolation_matrix` |
| S10 | No authentication; a session token is not an identity. | Architecture | **DOCUMENTED** (public mode = synthetic portfolio demo only; see §3) | — |
| S11 | Data at rest is not encrypted (SQLite). | Architecture | **DOCUMENTED** (§5) | — |
| S12 | Process-local state, so one worker and one instance; a restart ends all public sessions. | Architecture | **DOCUMENTED**, startup command updated | `test_state_is_process_local` |
| S13 | Uvicorn trusts `X-Forwarded-For` from `127.0.0.1` by default, so behind the Next.js proxy on the same host a client can choose the IP used for per-IP limits. | P3 | **MITIGATED** (global cap on new sessions independent of IP; per-session limits use the unforgeable token) and **DOCUMENTED** (`--forwarded-allow-ips`) | `test_global_session_cap_survives_ip_spoofing` |
| S14 | `script-src 'unsafe-inline'` in the CSP (Next.js hydration on statically prerendered pages). | P3 | **DOCUMENTED** (nonces would need dynamic rendering of every page) | — |

Verified and unchanged:
- CORS rejects unknown origins and sends no credentials.
- SQL is parameterised, with whitelisted identifiers.
- The Gemini key is server-side only and sent in a header, not in the URL.
- `.env*` files are git-ignored.
- The only `NEXT_PUBLIC_*` variables are public URLs.
- Errors return a generic 500, and only the exception type is logged (tested with a planted secret).
- `pip-audit -r requirements-api.txt` and `npm audit` reported no known vulnerabilities on 29 Oct 2026.

## 3. Access model: recommendation

**Option A: restricted portfolio demo (what Spendly implements).** This is right for a recruiter-facing deployment:
- the synthetic demo is clearly labelled;
- "My data" is per tab session, in memory, and expires;
- limits are strict and tokens are server-issued;
- nothing is written to disk in public mode (tested).

It **must not** be described as secure storage for real statements. The README and app say statements are best
analysed locally.

**Option B: personal accounts (not implemented).** Needed only if real users should upload real statements to a
hosted Spendly. Minimum requirements:
- an established identity provider (e.g. OIDC via the host, or a maintained library such as Auth.js on the Next.js
  side), with **HttpOnly, Secure, SameSite=Lax** session cookies and CSRF protection;
- server-side verification in FastAPI of a signed session or JWT on every request;
- an `owner_id` on statements, transactions, budgets, decisions and corrections (or a database per owner), enforced
  in every query;
- persistent storage with encryption at rest, backups and a retention policy;
- revocation and expiry, an audit log, and shared rate-limit and session state (e.g. Redis) if more than one worker.

This is a substantial architectural change and needs your decision on the identity provider and the hosting. It was
deliberately **not** improvised here.

## 4. Rate limits and request limits (public mode; local mode with `SPENDLY_RATE_LIMIT=true`)

| Bucket | Limit | Key |
|---|---|---|
| New session | 10/min per client IP **and** 60/min in total | IP (see S13) / global |
| Import preview (PDF parsing) | 10/min | session |
| Import commit | 20/min | session |
| PDF report | 20/min | session |
| CSV export | 30/min | session |
| Edits, bulk edits, budgets, reviews | 120/min | session |
| Delete all / demo reset / end session | 10/min | session |
| AI | 10/min | session |
| Other reads | 600/min | session |

Exceeding a limit returns `429` with `Retry-After`. The limiter is **process-local**: with N workers, the effective
limit is N× and counters reset on restart. It is not a distributed limiter.

Other limits:
- Upload: `SPENDLY_MAX_UPLOAD_MB` (10), checked from `Content-Length` before the body is read, and again after.
  Requests without a length are refused.
- PDF: at most 60 pages, `%PDF` signature, `.pdf` extension. Encrypted PDFs need the password; corrupt ones are rejected.
- JSON bodies: at most 64 KB.
- Pending imports: 3 per session, 100 in total, 30-minute expiry.
- Sessions: 200 at a time. Active ones are never evicted; a full server returns 503.

Not constrained: the CPU time of parsing a valid 60-page PDF (about 5 s per 1,000 rows on the test machine). A hard
timeout would need a worker process or pool.

## 5. Logging, storage and encryption

**Logs.** Spendly's own logs contain counts and exception types only. Uvicorn access lines keep method, path,
status and client IP, with query strings replaced by `?[redacted]`. Session tokens are headers and are not logged. Verified
against a real uvicorn process with a distinctive merchant name, a forged token, a 400, a 401 and an upload.
Remaining: the client IP stays in access logs (operational). If the host adds its own request logging, configure it
not to record query strings.

**Stored data.**
- Local mode: SQLite files in `SPENDLY_DATA_DIR` (default `./data`, git-ignored), now `0600`. They hold dates,
  amounts, **masked** descriptions and merchant names. PDFs are never stored, and there are no backups or exports
  on disk (CSV and PDF are streamed to the browser).
- Public mode: in-memory only (tested: nothing written to disk).

**Encryption at rest: not implemented.** File permissions are access control, **not** encryption. Options, in order of
effort:
1. Rely on full-disk or volume encryption from the OS or host (no code change; recommended for local use).
2. SQLCipher via `sqlcipher3`. It's a new native dependency, needs key management (where does the key live?), and
   existing files need migrating.
3. A managed database with encryption at rest. It needs Option B's ownership model first.

None of these is chosen yet, because each needs a hosting or key-management decision from the owner.

## 6. Browser security

Web (Next.js, `next.config.ts`):
- `Content-Security-Policy`: `default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';
  img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self';
  form-action 'self'; frame-ancestors 'none'` (dev adds `'unsafe-eval'` and `ws:` for hot reload);
- `X-Content-Type-Options`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: DENY`,
  `Permissions-Policy`, and no `X-Powered-By`.

API: `default-src 'none'; frame-ancestors 'none'` (except `/api/docs`), `no-store`, `nosniff`, `DENY`,
`Referrer-Policy: no-referrer`.

Verified locally:
- every page, chart, import, export and PDF download works under the CSP (70/70 browser checks);
- no CSP violations appear in the console;
- no third-party requests are made.

Requires the host: HTTPS and `Strict-Transport-Security`, and the production CORS origin.

## 7. Hosting configuration still required (not verifiable locally)

1. `SPENDLY_PUBLIC_DEPLOYMENT=true` on any shared host. Never set `SPENDLY_ALLOW_REMOTE=true` there.
2. `uvicorn api.main:app --workers 1 --forwarded-allow-ips <your proxy IP>`, with a single instance (no autoscaling).
3. `SPENDLY_CORS_ORIGINS=https://<your web origin>`.
4. HTTPS on both hosts, plus `Strict-Transport-Security` at the web host.
5. The host's own request-body limit should be ≥ `SPENDLY_MAX_UPLOAD_MB`, and it shouldn't log query strings.
6. Keep `/api/docs` off (the default when public).
7. Encrypted volumes if you ever run local mode on a server (not recommended).
8. Expect public sessions to end on every deploy or restart.

## 8. Verification (final run)

| Check | Result |
|---|---|
| `pytest` | 429 passed (395 earlier + 34 security tests), 0 failed |
| Coverage (`--cov=src --cov=api`) | 89% overall; `api/main.py` 95%, `api/security.py` 96%, `api/state.py` 97% |
| `npm run lint` / `npx tsc --noEmit` / `npm run build` | exit 0 / 0 / 0 |
| Browser E2E, local mode, incl. Streamlit | 70 passed, 0 failed |
| Browser E2E, public mode (journey P) | 7 passed, 0 failed |
| Known-answer financial, integrity and report tests | 97 passed |
| `pip-audit -r requirements-api.txt` / `npm audit` | no known vulnerabilities / 0 vulnerabilities |

## 9. Verdict for the assessed scope: PASS WITH LIMITATIONS

The confirmed issues S1–S9 are fixed or mitigated, with regression tests, and cross-session isolation is verified
by API tests and in the browser. No known release-blocking defect remains **for the intended use: a synthetic-data
portfolio demo, or single-user local use**. These remain:
- no authentication;
- no encryption at rest;
- single-process state;
- `'unsafe-inline'` scripts;
- host-dependent settings (§7).

For real personal statements on a shared host, Option B (§3) is a prerequisite.
