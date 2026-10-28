"use client";

import {
  AlertTriangle, CheckCircle2, Download, FileSearch, FlaskConical, KeyRound, Lock, RotateCcw, ShieldCheck, Sparkles, Trash2,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Pill } from "@/components/ui/badges";
import { Button, buttonClass } from "@/components/ui/button";
import { Card, SectionHeader } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { UploadDropzone } from "@/components/ui/upload-dropzone";
import { ApiError, apiSend, apiUpload, downloadFile } from "@/lib/api";
import { fmtDate, inr, TYPE_LABELS } from "@/lib/format";
import { useApp } from "@/lib/store";
import type { CommitResult, ImportPreview, ImportReport, PreviewRow } from "@/lib/types";

const STEPS = ["Choose PDF", "Read & check", "Review preview", "Import"] as const;

function Stepper({ step }: { step: number }) {
  return (
    <ol className="flex flex-wrap items-center gap-x-2 gap-y-2 text-[0.78rem]" aria-label="Import progress">
      {STEPS.map((label, i) => {
        const state = i < step ? "done" : i === step ? "current" : "todo";
        return (
          <li key={label} className="flex items-center gap-2" aria-current={state === "current" ? "step" : undefined}>
            <span className={`flex h-6 w-6 items-center justify-center rounded-full border text-[0.7rem] font-semibold ${
              state === "done" ? "border-lime bg-lime text-ink" : state === "current" ? "border-lime text-lime" : "border-line-2 text-faint"}`}>
              {state === "done" ? <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" /> : i + 1}
            </span>
            <span className={state === "todo" ? "text-faint" : "text-fg"}>{label}</span>
            {i < STEPS.length - 1 ? <span className="mx-1 hidden h-px w-6 bg-line-2 sm:block" aria-hidden="true" /> : null}
          </li>
        );
      })}
    </ol>
  );
}

function rowWarning(r: PreviewRow): string | null {
  if (r.duplicate_status === "exact_in_file") return "Repeated row. Will be skipped.";
  if (r.duplicate_status === "exact_existing") return "Already imported. Will be skipped.";
  if (r.duplicate_status === "possible") return "Possible duplicate. Imported and flagged.";
  return r.review_reason;
}

function DemoPanel() {
  const { setMode, refresh, notify } = useApp();
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const reset = async () => {
    setBusy(true);
    try {
      await apiSend("/api/demo/reset", "POST");
      notify("Demo data reset to the original sample.");
      refresh();
    } catch (e) {
      notify(e instanceof ApiError ? e.message : "Couldn't reset the demo.", "error");
    } finally {
      setBusy(false);
      setConfirm(false);
    }
  };
  return (
    <Card className="p-5 sm:p-7">
      <div className="flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
        <div className="max-w-2xl">
          <p className="eyebrow flex items-center gap-2 text-warn"><FlaskConical className="h-3.5 w-3.5" aria-hidden="true" />Demo mode</p>
          <h2 className="mt-2 text-xl font-semibold tracking-tight">You&apos;re viewing synthetic sample data</h2>
          <p className="mt-2 text-[0.9rem] leading-relaxed text-muted">
            Six invented months (April–September 2026) built to show every feature: salary, refunds, own-account transfers,
            card bills, subscriptions, a repeated row, uncategorized local shops and one unusually large purchase.
            None of it is anyone&apos;s real money. To import your own statement, switch to <b className="text-fg">My data</b>. It&apos;s stored separately and never mixed with the demo.
          </p>
        </div>
        <div className="flex shrink-0 flex-col gap-2 sm:flex-row md:flex-col">
          <Button variant="primary" onClick={() => setMode("user")}><Lock className="h-4 w-4" aria-hidden="true" />Switch to My data</Button>
          <Button onClick={() => setConfirm(true)}><RotateCcw className="h-4 w-4" aria-hidden="true" />Reset demo data</Button>
        </div>
      </div>
      <div className="mt-6 border-t border-line pt-5">
        <p className="text-[0.85rem] font-medium text-fg">Try the import flow with synthetic PDFs</p>
        <p className="mt-1 text-[0.8rem] text-muted">Download one, switch to My data, and upload it.</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <a href="/samples/sample_bank_statement.pdf" download className={buttonClass("secondary", "sm")}><Download className="h-3.5 w-3.5" aria-hidden="true" />Sample bank statement</a>
          <a href="/samples/sample_phonepe_statement.pdf" download className={buttonClass("secondary", "sm")}><Download className="h-3.5 w-3.5" aria-hidden="true" />Sample PhonePe statement</a>
        </div>
      </div>
      <ConfirmDialog open={confirm} title="Reset demo data?" confirmLabel="Reset" busy={busy} onConfirm={reset} onCancel={() => setConfirm(false)}>
        This undoes your edits to the demo (categories, reviews, decisions) and reloads the original synthetic sample. Your own data isn&apos;t affected.
      </ConfirmDialog>
    </Card>
  );
}

function ImportFlow() {
  const { meta, refresh, notify } = useApp();
  const [file, setFile] = useState<File | null>(null);
  const [password, setPassword] = useState("");
  const [needsPassword, setNeedsPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reading, setReading] = useState(false);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [onlyWarnings, setOnlyWarnings] = useState(false);
  const [includeDups, setIncludeDups] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [result, setResult] = useState<CommitResult | null>(null);

  const step = result ? 4 : preview ? 2 : file ? 1 : 0;

  const reset = () => {
    if (preview) apiSend(`/api/import/${preview.token}`, "DELETE").catch(() => {});
    setFile(null); setPassword(""); setNeedsPassword(false); setError(null); setPreview(null); setResult(null); setIncludeDups(false);
  };

  const read = async () => {
    if (!file) return;
    setReading(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      if (password) form.append("password", password);
      setPreview(await apiUpload<ImportPreview>("/api/import/preview", form));
      setNeedsPassword(false);
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(0, "Couldn't read this file.");
      if (err.status === 401) setNeedsPassword(true);
      setError(err.message);
    } finally {
      setReading(false);
    }
  };

  const suggest = async () => {
    if (!preview) return;
    setAiBusy(true);
    try {
      const res = await apiSend<{ changed: number; preview: ImportPreview }>(`/api/import/${preview.token}/ai`, "POST");
      setPreview(res.preview);
      notify(`${res.changed} row(s) received an AI-suggested category, marked for review.`, "info");
    } catch (e) {
      notify(e instanceof ApiError ? e.message : "AI suggestions failed. Rule-based categories are kept.", "error");
    } finally {
      setAiBusy(false);
    }
  };

  const commit = async () => {
    if (!preview) return;
    setCommitting(true);
    try {
      const res = await apiSend<CommitResult>(`/api/import/${preview.token}/commit`, "POST", { include_exact_duplicates: includeDups });
      setResult(res);
      setPreview(null);
      refresh();
      notify(`Imported ${res.imported} transactions.`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The import failed and nothing was saved.");
    } finally {
      setCommitting(false);
    }
  };

  const rows = preview ? (onlyWarnings ? preview.rows.filter((r) => rowWarning(r)) : preview.rows) : [];

  return (
    <Card className="p-5 sm:p-7">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <SectionHeader title="Import a statement" subtitle="Nothing is saved until you confirm. The PDF itself is never stored." />
        <Stepper step={step} />
      </div>

      {/* ---------- done */}
      {result ? (
        <div className="mt-6 rounded-2xl border border-lime/25 bg-lime/[0.04] p-5" role="status">
          <p className="flex items-center gap-2 text-[1rem] font-semibold text-fg"><CheckCircle2 className="h-5 w-5 text-lime" aria-hidden="true" />Import complete</p>
          <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
            {[["Imported", result.imported], ["Duplicates skipped", result.skipped_duplicates], ["Flagged for review", result.flagged_for_review], ["Unreadable rows", result.invalid]].map(([k, v]) => (
              <div key={k as string}><dt className="eyebrow text-[0.6rem]">{k}</dt><dd className="tabular mt-1 text-xl font-semibold">{v}</dd></div>
            ))}
          </dl>
          <div className="mt-5 flex flex-wrap gap-2">
            <Link href="/app" className={buttonClass("primary")}>Open overview</Link>
            {result.flagged_for_review ? <Link href="/app/transactions?status=needs_review" className={buttonClass("secondary")}>Review flagged rows</Link> : null}
            <Button variant="ghost" onClick={reset}>Import another statement</Button>
          </div>
        </div>
      ) : null}

      {/* ---------- choose + read */}
      {!result && !preview ? (
        <div className="mt-6 grid gap-5 lg:grid-cols-[1.3fr_1fr]">
          <UploadDropzone maxMb={meta?.upload.max_mb ?? 10} file={file} disabled={reading}
            onFile={(f, err) => { setFile(f); setError(err ?? null); setNeedsPassword(false); }} />
          <div className="flex flex-col gap-4">
            <label className="text-[0.8rem] font-medium text-muted">
              <span className="flex items-center gap-2"><KeyRound className="h-3.5 w-3.5" aria-hidden="true" />PDF password <span className="font-normal text-faint">(only if the statement is protected)</span></span>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="off"
                aria-invalid={needsPassword || undefined}
                className={`mt-1.5 h-11 w-full rounded-xl border bg-ink-2 px-3 text-[0.9rem] text-fg ${needsPassword ? "border-warn/60" : "border-line"}`} />
              <span className="mt-1 block text-[0.72rem] font-normal text-faint">Used once to open the file. Never stored.</span>
            </label>
            {error ? (
              <p role="alert" className="flex items-start gap-2 rounded-xl border border-err/30 bg-err/5 p-3 text-[0.84rem] text-fg/90">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[#ff9b8f]" aria-hidden="true" />{error}
              </p>
            ) : null}
            <Button variant="primary" onClick={read} loading={reading} disabled={!file}>
              <FileSearch className="h-4 w-4" aria-hidden="true" />{reading ? "Reading statement…" : "Read statement"}
            </Button>
            <div className="rounded-xl border border-line bg-ink-2/70 p-3 text-[0.76rem] leading-relaxed text-muted">
              <p className="font-medium text-fg/90">Supported formats</p>
              <ul className="mt-1 list-disc space-y-0.5 pl-4">{meta?.upload.formats.map((f) => <li key={f}>{f}</li>)}</ul>
              <p className="mt-1.5">Text-based PDFs up to {meta?.upload.max_mb} MB / {meta?.upload.max_pages} pages. Scanned or photographed PDFs aren&apos;t supported.</p>
            </div>
          </div>
        </div>
      ) : null}

      {/* ---------- preview */}
      {preview ? (
        <div className="mt-6 space-y-5">
          <div className="flex flex-wrap items-center gap-2 text-[0.82rem] text-muted">
            <Pill tone="lime">{preview.parser.label}</Pill>
            <span>Period {fmtDate(preview.period.start)} – {fmtDate(preview.period.end)}</span>
            {preview.balance_check.checked_pairs ? (
              <span>· balance check: {preview.balance_check.mismatches} mismatch{preview.balance_check.mismatches === 1 ? "" : "es"} in {preview.balance_check.checked_pairs} pairs</span>
            ) : null}
          </div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            {[
              ["Rows found", preview.counts.extracted, `${preview.counts.invalid} unreadable`],
              ["Ready to import", preview.counts.to_import, "after skipping exact duplicates"],
              ["Exact duplicates", preview.counts.exact_duplicates, "will be skipped"],
              ["Possible duplicates", preview.counts.possible_duplicates, "imported & flagged"],
              ["Uncategorized", preview.counts.uncategorized, "fix later in Transactions"],
            ].map(([k, v, n]) => (
              <div key={k as string} className="rounded-xl border border-line bg-ink-2/70 p-3.5">
                <p className="eyebrow text-[0.58rem]">{k}</p><p className="tabular mt-1 text-xl font-semibold">{v}</p><p className="mt-0.5 text-[0.7rem] text-faint">{n}</p>
              </div>
            ))}
          </div>

          {preview.warnings.length ? (
            <ul className="space-y-2">{preview.warnings.map((w) => (
              <li key={w} className="flex items-start gap-2 rounded-xl border border-warn/25 bg-warn/[0.05] px-3 py-2.5 text-[0.84rem] text-fg/90">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn" aria-hidden="true" />{w}</li>))}</ul>
          ) : null}

          <ValidationReport report={preview.report} />

          <div className="flex flex-wrap items-center justify-between gap-3">
            <label className="flex items-center gap-2 text-[0.84rem] text-muted">
              <input type="checkbox" checked={onlyWarnings} onChange={(e) => setOnlyWarnings(e.target.checked)} className="h-4 w-4 accent-[#c6ff5e]" />
              Show only rows with warnings
            </label>
            {preview.ai.enabled && preview.ai.uncategorized_merchants ? (
              <Button size="sm" onClick={suggest} loading={aiBusy} title={`Sends only: ${preview.ai.payload.join(", ")}`}>
                <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />Suggest categories with AI ({preview.ai.uncategorized_merchants})
              </Button>
            ) : null}
          </div>
          {preview.ai.enabled && preview.ai.uncategorized_merchants ? (
            <p className="-mt-2 text-[0.72rem] text-faint">AI receives only these sanitized merchant labels: {preview.ai.payload.join(", ") || "none"}. No amounts, dates or account details are sent.</p>
          ) : null}

          <div className="max-h-[480px] overflow-auto rounded-2xl border border-line">
            <table className="w-full min-w-[760px] text-left text-[0.8rem]">
              <caption className="sr-only">Preview of extracted transactions</caption>
              <thead className="sticky top-0 border-b border-line bg-card text-[0.7rem] text-muted"><tr>
                {["Date", "Merchant / description", "Amount", "Type", "Category", "Warnings"].map((h, i) => (
                  <th key={h} scope="col" className={`px-3 py-2.5 font-medium ${i === 2 ? "text-right" : ""}`}>{h}</th>))}
              </tr></thead>
              <tbody>{rows.map((r) => {
                const warn = rowWarning(r);
                const skipped = r.duplicate_status.startsWith("exact") && !includeDups;
                return (
                  <tr key={r.row_number} className={`border-b border-line/60 last:border-0 ${skipped ? "opacity-50" : ""}`}>
                    <td className="tabular px-3 py-2 whitespace-nowrap text-muted">{fmtDate(r.date)}</td>
                    <td className="max-w-[18rem] px-3 py-2"><p className="truncate text-fg">{r.merchant}</p>
                      <p className="truncate font-mono text-[0.66rem] text-faint" title={r.description}>{r.description}</p></td>
                    <td className={`tabular px-3 py-2 text-right whitespace-nowrap ${r.direction === "credit" ? "text-pos" : "text-fg"}`}>
                      {inr(r.direction === "credit" ? r.amount_paise : -r.amount_paise, { sign: true, decimals: true })}</td>
                    <td className="px-3 py-2 whitespace-nowrap text-muted">{TYPE_LABELS[r.type] ?? r.type}</td>
                    <td className="px-3 py-2 whitespace-nowrap text-fg/85">{r.category}{r.method === "ai" ? <span className="ml-1 text-[0.68rem] text-lime">AI</span> : null}</td>
                    <td className="px-3 py-2 text-[0.74rem]">{warn ? <span className="flex items-start gap-1.5 text-warn"><AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />{warn}</span> : <span className="text-faint">—</span>}</td>
                  </tr>
                );
              })}</tbody>
            </table>
            {rows.length === 0 ? <p className="p-4 text-[0.84rem] text-muted">No rows with warnings.</p> : null}
          </div>

          {preview.invalid_rows.length ? (
            <details className="rounded-xl border border-line bg-ink-2/60 p-3 text-[0.82rem]">
              <summary className="cursor-pointer text-fg">{preview.invalid_rows.length} row(s) couldn&apos;t be read and won&apos;t be imported</summary>
              <ul className="mt-2 space-y-1 text-muted">{preview.invalid_rows.map((r) => <li key={r.row_number}>Row {r.row_number}{r.page ? ` (page ${r.page})` : ""}: {r.reason}</li>)}</ul>
            </details>
          ) : null}

          {error ? <p role="alert" className="text-[0.84rem] text-[#ff9b8f]">{error}</p> : null}

          <div className="flex flex-col gap-3 border-t border-line pt-5 sm:flex-row sm:items-center sm:justify-between">
            {preview.counts.exact_duplicates ? (
              <label className="flex items-center gap-2 text-[0.82rem] text-muted">
                <input type="checkbox" checked={includeDups} onChange={(e) => setIncludeDups(e.target.checked)} className="h-4 w-4 accent-[#c6ff5e]" />
                Import exact duplicates anyway (not recommended)
              </label>
            ) : <span />}
            <div className="flex flex-col-reverse gap-2 sm:flex-row">
              <Button variant="ghost" onClick={reset}>Discard</Button>
              <Button variant="primary" onClick={commit} loading={committing} disabled={preview.already_imported || preview.counts.to_import + (includeDups ? preview.counts.exact_duplicates : 0) === 0}>
                Import {preview.counts.to_import + (includeDups ? preview.counts.exact_duplicates : 0)} transactions
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </Card>
  );
}

function Settings() {
  const { mode, meta, refresh, notify } = useApp();
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const del = async () => {
    setBusy(true);
    try {
      await apiSend("/api/data", "DELETE", { confirm: typed });
      notify("All imported data deleted.");
      refresh();
      setOpen(false);
      setTyped("");
    } catch (e) {
      notify(e instanceof ApiError ? e.message : "Couldn't delete the data.", "error");
    } finally {
      setBusy(false);
    }
  };
  const storage = meta?.storage === "memory" ? "This browser session's private, in-memory database. It disappears when the session ends."
    : mode === "demo" ? "A separate demo database with synthetic data only."
    : "An unencrypted SQLite file on the computer running Spendly (data/spendly_user.db).";

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
      <Card className="p-5 sm:p-6">
        <SectionHeader title="Privacy & storage" />
        <ul className="mt-4 space-y-3 text-[0.85rem] leading-relaxed text-muted">
          <li className="flex gap-3"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-lime-2" aria-hidden="true" /><span><b className="font-medium text-fg">PDFs are never stored.</b> Statements are parsed in memory. Only the extracted transactions are saved after you confirm.</span></li>
          <li className="flex gap-3"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-lime-2" aria-hidden="true" /><span><b className="font-medium text-fg">Identifiers are masked</b> before saving: account, card and reference numbers become XXXX1234, and UPI IDs and phone numbers are replaced.</span></li>
          <li className="flex gap-3"><Lock className="mt-0.5 h-4 w-4 shrink-0 text-lime-2" aria-hidden="true" /><span><b className="font-medium text-fg">Where your data lives:</b> {storage}</span></li>
        </ul>
      </Card>
      <Card className="p-5 sm:p-6">
        <SectionHeader title="AI (optional)" />
        <p className="mt-3 flex items-center gap-2 text-[0.88rem] text-fg"><Sparkles className={`h-4 w-4 ${meta?.ai.enabled ? "text-lime" : "text-faint"}`} aria-hidden="true" />
          {meta?.ai.enabled ? "AI features are on" : "AI features are off"}</p>
        <p className="mt-2 text-[0.82rem] leading-relaxed text-muted">{meta?.ai.message}</p>
        <p className="mt-3 text-[0.78rem] leading-relaxed text-faint">
          AI is a server setting (<code className="font-mono">SPENDLY_ENABLE_AI</code> + <code className="font-mono">GEMINI_API_KEY</code>), so keys never reach the browser.
          When it&apos;s on, it can suggest categories for unknown merchants (sanitized names only) and summarise insights. Any AI text containing a number that
          wasn&apos;t calculated by Spendly is rejected.
        </p>
      </Card>
      <Card className="p-5 sm:p-6">
        <SectionHeader title="Export" />
        <p className="mt-3 text-[0.84rem] text-muted">Download every transaction in the current data source as CSV (amounts in rupees, identifiers masked).</p>
        <Button className="mt-4" onClick={() => downloadFile("/api/transactions/export.csv", "spendly_transactions.csv").then(() => notify("Export downloaded.")).catch(() => notify("Export failed.", "error"))}>
          <Download className="h-4 w-4" aria-hidden="true" />Export all transactions
        </Button>
      </Card>
      <Card className="border-err/25 p-5 sm:p-6">
        <SectionHeader title="Delete my data" />
        <p className="mt-3 text-[0.84rem] text-muted">
          {mode === "user" ? "Permanently removes every imported statement, transaction, correction and decision from My data. The demo isn't affected."
            : "Switch to My data to delete your imported data. Demo data can only be reset."}
        </p>
        <Button className="mt-4" variant="danger" disabled={mode !== "user" || !meta?.counts.statements} onClick={() => setOpen(true)}>
          <Trash2 className="h-4 w-4" aria-hidden="true" />Delete all my data
        </Button>
      </Card>
      <ConfirmDialog open={open} title="Delete all your data?" tone="danger" confirmLabel="Delete permanently" busy={busy}
        confirmDisabled={typed !== "DELETE"} onConfirm={del} onCancel={() => { setOpen(false); setTyped(""); }}>
        <p>This permanently deletes {meta?.counts.transactions ?? 0} transactions from {meta?.counts.statements ?? 0} statement(s). It can&apos;t be undone.</p>
        <label className="mt-4 block text-[0.8rem] text-fg">Type <b>DELETE</b> to confirm
          <input value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" aria-label="Type DELETE to confirm"
            className="mt-1.5 h-10 w-full rounded-xl border border-line bg-ink-2 px-3 text-fg" />
        </label>
      </ConfirmDialog>
    </div>
  );
}

/** Structured validation report for this import (computed by the API; shown as-is). */
function ValidationReport({ report: r }: { report: ImportReport }) {
  const rejected = r.issues.filter((i) => i.code in r.rejected_by_reason);
  const rec = r.reconciliation;
  const items: [string, string][] = [
    ["Extracted", `${r.rows_extracted} rows`],
    ["Rejected", rejected.length ? rejected.map((i) => `${i.label} ${i.count}`).join(", ") : "none"],
    ["Accepted", `${r.rows_accepted} = ${r.rows_to_import} to import + ${r.exact_duplicates_skipped} exact duplicate${r.exact_duplicates_skipped === 1 ? "" : "s"}`],
    ["Possible duplicates", `${r.flags.possible_duplicates} (imported and flagged)`],
    ["Uncategorised", String(r.flags.uncategorised)],
    ["Running balance", r.balance_check.available ? `${r.balance_check.mismatches} of ${r.balance_check.checked_pairs} pairs don't add up` : "no balance column: not checkable"],
    ["Opening → closing", !rec.available ? "balances not printed: not checkable"
      : rec.reconciled ? `reconciles (${inr(rec.opening_paise, { decimals: true })} → ${inr(rec.closing_paise, { decimals: true })})`
      : `off by ${inr(Math.abs(rec.difference_paise ?? 0), { decimals: true })}`],
  ];
  return (
    <details className="rounded-xl border border-line bg-ink-2/60 p-3 text-[0.82rem]" open={r.rows_rejected > 0 || rec.reconciled === false}>
      <summary className="cursor-pointer text-fg">Validation report</summary>
      <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
        {items.map(([k, v]) => (
          <div key={k} className="flex flex-col"><dt className="text-[0.72rem] text-faint">{k}</dt><dd className="tabular text-fg/90">{v}</dd></div>
        ))}
      </dl>
    </details>
  );
}

export default function ImportPage() {
  const { mode } = useApp();
  return (
    <div className="space-y-8">
      {mode === "demo" ? <DemoPanel /> : <ImportFlow />}
      <section aria-labelledby="settings-title" className="space-y-4">
        <h2 id="settings-title" className="text-[1.05rem] font-semibold tracking-tight">Settings</h2>
        <Settings />
      </section>
    </div>
  );
}
