"use client";

import { ArrowRight, CheckCircle2, CopyX, FileWarning, Scale, Tags, Wallet } from "lucide-react";
import { NoDataState } from "@/components/app/no-data";
import { Pill } from "@/components/ui/badges";
import { Card, SectionHeader } from "@/components/ui/card";
import { MetricCard } from "@/components/ui/metric-card";
import { ErrorState, Skeleton } from "@/components/ui/states";
import { fmtDate, inr } from "@/lib/format";
import { useFiltered, useOpenTransactions } from "@/lib/hooks";
import { useApp } from "@/lib/store";
import type { InsightLink, QualityResponse } from "@/lib/types";

type Check = {
  key: string;
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  count: number;
  ok: string;
  explain: string;
  link?: InsightLink;
  linkLabel?: string;
};

export default function QualityPage() {
  const { meta } = useApp();
  const { data, error, initialLoading, reload } = useFiltered<QualityResponse>("/api/quality", {}, false);
  const openTransactions = useOpenTransactions();

  if (meta && meta.counts.transactions === 0) return <NoDataState />;
  if (error && !data) return <ErrorState message={error.message} onRetry={reload} />;
  if (initialLoading || !data) return <div className="space-y-4" role="status" aria-label="Loading"><Skeleton className="h-32" /><Skeleton className="h-72" /></div>;

  const c = data.counts;
  const checks: Check[] = [
    { key: "dups", icon: CopyX, title: "Possible duplicates", count: c.possible_duplicates, ok: "No possible duplicates waiting.",
      explain: "Same date, amount and merchant as another row, but no running balance or transaction ID to prove it's a copy. Identical payments can be genuine (two coffees), so nothing is removed automatically.",
      link: { statuses: ["possible_duplicate"] }, linkLabel: "Review duplicates" },
    { key: "uncat", icon: Tags, title: "Uncategorized transactions", count: c.uncategorized, ok: "Everything has a category.",
      explain: "No rule matched these merchants (often local shops or people). They count as “Other” until you set a category. One correction can apply to every row from that merchant.",
      link: { statuses: ["uncategorized"] }, linkLabel: "Categorize" },
    { key: "review", icon: FileWarning, title: "Rows needing review", count: c.needs_review, ok: "Nothing needs review.",
      explain: "Includes uncategorized rows, possible duplicates, AI-suggested categories and credits from shops treated as refunds.",
      link: { statuses: ["needs_review"] }, linkLabel: "Open review list" },
    { key: "balance", icon: Scale, title: "Running-balance mismatches", count: c.balance_mismatches,
      ok: c.balance_checked_pairs ? "Every checked row adds up." : "No balance column in your statements, so this couldn't be checked.",
      explain: `For consecutive rows, previous balance ± amount should equal the printed balance. ${c.balance_mismatches} of ${c.balance_checked_pairs} checked pairs didn't. That usually means a row was mis-read, repeated or is missing.` },
    { key: "invalid", icon: FileWarning, title: "Rows that couldn't be imported", count: c.rows_invalid, ok: "Every extracted row was readable.",
      explain: "Rows with a missing or unreadable date, amount or description were left out. Ambiguous dates are never guessed. See the reasons below." },
    { key: "balance-missing", icon: Wallet, title: "Rows without a running balance", count: c.rows_without_balance, ok: "Every row has a balance.",
      explain: "Common for UPI app statements. Duplicate detection then relies on transaction IDs, and the balance check can't run." },
  ];

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <MetricCard label="Rows extracted" value={c.rows_extracted.toLocaleString("en-IN")} note={`${data.statements.length} statement${data.statements.length === 1 ? "" : "s"}`}
          tip="Every row the parser found in your imported files, before validation." />
        <MetricCard label="Transactions saved" value={c.transactions.toLocaleString("en-IN")} note={`${c.manual_corrections} manual correction${c.manual_corrections === 1 ? "" : "s"}`} />
        <MetricCard label="Duplicates skipped" value={c.duplicates_skipped.toLocaleString("en-IN")} note="exact copies, not imported"
          tip="Rows identical to another row including the running balance or transaction ID, for example from overlapping statements." />
        <MetricCard label="Balance check" value={c.balance_checked_pairs ? `${c.balance_mismatches} / ${c.balance_checked_pairs}` : "n/a"}
          note={c.balance_checked_pairs ? "mismatches / pairs checked" : "no balance column"}
          tip="How many consecutive row pairs failed the running-balance check, out of those that could be checked." />
      </div>

      <section aria-labelledby="checks-title" className="space-y-4">
        <SectionHeader id="checks-title" title="Checks" subtitle="Every count comes from the import validation. Nothing here is an estimate." />
        <ul className="grid gap-3 lg:grid-cols-2">
          {checks.map((k) => {
            const Icon = k.icon;
            const clean = k.count === 0;
            return (
              <li key={k.key}>
                <Card as="article" className="flex h-full flex-col p-4 sm:p-5">
                  <div className="flex items-start justify-between gap-3">
                    <h3 className="flex items-center gap-2.5 text-[0.95rem] font-semibold text-fg">
                      <Icon className={`h-4 w-4 ${clean ? "text-pos" : "text-warn"}`} aria-hidden="true" />{k.title}
                    </h3>
                    {clean ? <Pill tone="pos"><CheckCircle2 className="h-3 w-3" aria-hidden="true" />OK</Pill>
                      : <Pill tone="warn"><span className="tabular">{k.count}</span> to check</Pill>}
                  </div>
                  <p className="mt-2.5 flex-1 text-[0.84rem] leading-relaxed text-muted">{clean ? k.ok : k.explain}</p>
                  {!clean && k.link ? (
                    <button type="button" onClick={() => openTransactions(k.link!)}
                      className="group mt-3 inline-flex items-center gap-1 self-start rounded-lg px-1.5 py-1 text-[0.8rem] font-medium text-lime hover:bg-lime/10">
                      {k.linkLabel} <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
                    </button>
                  ) : null}
                </Card>
              </li>
            );
          })}
        </ul>
      </section>

      {data.issues.length ? (
        <section aria-labelledby="issues-title" className="space-y-4">
          <SectionHeader id="issues-title" title="Rows that couldn't be imported"
            subtitle={data.issue_breakdown.map((b) => `${b.kind}: ${b.count}`).join(" · ")} />
          <Card className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-left text-[0.82rem]">
              <thead className="border-b border-line text-[0.72rem] text-muted"><tr>
                <th scope="col" className="px-4 py-3 font-medium">Statement</th><th scope="col" className="px-4 py-3 font-medium">Page</th>
                <th scope="col" className="px-4 py-3 font-medium">Row</th><th scope="col" className="px-4 py-3 font-medium">Reason</th></tr></thead>
              <tbody>{data.issues.map((i, n) => (
                <tr key={n} className="border-b border-line/60 last:border-0">
                  <td className="px-4 py-2.5 text-fg">{i.statement}</td><td className="tabular px-4 py-2.5 text-muted">{i.page ?? "—"}</td>
                  <td className="tabular px-4 py-2.5 text-muted">{i.row_number ?? "—"}</td><td className="px-4 py-2.5 text-fg/85">{i.reason}</td>
                </tr>))}</tbody>
            </table>
          </Card>
        </section>
      ) : null}

      <section aria-labelledby="statements-title" className="space-y-4">
        <SectionHeader id="statements-title" title="Imported statements" />
        <Card className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-[0.82rem]">
            <thead className="border-b border-line text-[0.72rem] text-muted"><tr>
              {["Statement", "Format", "Period", "Extracted", "Imported", "Invalid", "Duplicates skipped", "Balance check", "Imported on"].map((h, i) => (
                <th key={h} scope="col" className={`px-4 py-3 font-medium ${i >= 3 && i <= 7 ? "text-right" : ""}`}>{h}</th>))}
            </tr></thead>
            <tbody>{data.statements.map((s) => (
              <tr key={s.id} className="border-b border-line/60 align-top last:border-0">
                <td className="px-4 py-3 text-fg">{s.display_name}
                  {s.warnings.length ? <ul className="mt-1 space-y-0.5 text-[0.72rem] text-warn">{s.warnings.map((w) => <li key={w}>{w}</li>)}</ul> : null}</td>
                <td className="px-4 py-3 text-muted">{s.parser_name}</td>
                <td className="px-4 py-3 whitespace-nowrap text-muted">{fmtDate(s.statement_period_start)} – {fmtDate(s.statement_period_end)}</td>
                <td className="tabular px-4 py-3 text-right">{s.rows_extracted}</td>
                <td className="tabular px-4 py-3 text-right">{s.rows_imported}</td>
                <td className="tabular px-4 py-3 text-right">{s.rows_invalid}</td>
                <td className="tabular px-4 py-3 text-right">{s.rows_skipped_duplicates}</td>
                <td className="tabular px-4 py-3 text-right">{s.balance_checked_pairs ? `${s.balance_mismatches}/${s.balance_checked_pairs}` : "n/a"}</td>
                <td className="px-4 py-3 whitespace-nowrap text-muted">{fmtDate(s.created_at.slice(0, 10))}</td>
              </tr>))}</tbody>
          </table>
        </Card>
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        <section aria-labelledby="uncat-title" className="space-y-4">
          <SectionHeader id="uncat-title" title="Uncategorized merchants" subtitle="Fix one row and apply it to the whole merchant" />
          <Card className="p-2">
            {data.uncategorized.length === 0 ? <p className="p-3 text-[0.84rem] text-muted">Everything is categorized.</p> : (
              <ul className="divide-y divide-line/60">{data.uncategorized.map((u) => (
                <li key={u.merchant + u.direction}>
                  <button type="button" onClick={() => openTransactions({ merchants: [u.merchant] })}
                    className="group flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2.5 text-left hover:bg-white/[0.03]">
                    <span className="min-w-0"><span className="block truncate text-[0.86rem] text-fg">{u.merchant}</span>
                      <span className="text-[0.72rem] text-faint">{u.transaction_count} {u.direction === "debit" ? "payments" : "credits"} · last {fmtDate(u.last_seen)}</span></span>
                    <span className="tabular flex items-center gap-2 text-[0.85rem] text-fg/85">{inr(u.total_paise)}
                      <ArrowRight className="h-3.5 w-3.5 text-faint transition-transform group-hover:translate-x-0.5" aria-hidden="true" /></span>
                  </button>
                </li>))}</ul>
            )}
          </Card>
        </section>
        <section aria-labelledby="corr-title" className="space-y-4">
          <SectionHeader id="corr-title" title="Manual corrections" subtitle="Your latest changes (audit log)" />
          <Card className="p-2">
            {data.corrections.length === 0 ? <p className="p-3 text-[0.84rem] text-muted">No manual corrections yet.</p> : (
              <ul className="divide-y divide-line/60">{data.corrections.map((m, i) => (
                <li key={i} className="px-3 py-2.5 text-[0.82rem]">
                  <span className="text-fg">{m.merchant}</span> <span className="text-faint">· {m.field.replace("_", " ")}</span>
                  <p className="mt-0.5 text-[0.76rem] text-muted"><span className="line-through decoration-faint">{m.old_value}</span> → <span className="text-fg/90">{m.new_value}</span>
                    <span className="ml-2 text-faint">{fmtDate(m.corrected_at.slice(0, 10))}</span></p>
                </li>))}</ul>
            )}
          </Card>
        </section>
      </div>
    </div>
  );
}
