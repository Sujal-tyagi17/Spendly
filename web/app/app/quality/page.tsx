"use client";

import { useReducedMotion } from "motion/react";
import { AlertOctagon, AlertTriangle, ArrowRight, CheckCircle2, Info, MinusCircle } from "lucide-react";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartContainer } from "@/components/app/charts";
import { NoDataState } from "@/components/app/no-data";
import { Pill } from "@/components/ui/badges";
import { Card, SectionHeader } from "@/components/ui/card";
import { InfoTip } from "@/components/ui/info-tip";
import { ErrorState, Skeleton } from "@/components/ui/states";
import { useApi } from "@/lib/api";
import { fmtDate, inr } from "@/lib/format";
import { useOpenTransactions } from "@/lib/hooks";
import { useApp } from "@/lib/store";
import type { QualityDimension, QualityResponse, Severity } from "@/lib/types";

const SEVERITY: Record<Severity, { label: string; tone: "neg" | "warn" | "neutral"; icon: typeof Info; text: string }> = {
  error: { label: "Error", tone: "neg", icon: AlertOctagon, text: "Data was not imported, or totals don't reconcile" },
  warning: { label: "Warning", tone: "warn", icon: AlertTriangle, text: "Imported, but may be wrong or double-counted: review it" },
  info: { label: "Info", tone: "neutral", icon: Info, text: "A check couldn't run, or a limitation of the format" },
};

const selectCls = "h-10 rounded-xl border border-line bg-ink-2 px-3 text-[0.84rem] text-fg";
const pctText = (v: number | null) => (v === null ? "n/a" : `${v.toFixed(1)}%`);

function SeverityPill({ s }: { s: Severity }) {
  const m = SEVERITY[s];
  const Icon = m.icon;
  return <Pill tone={m.tone}><Icon className="h-3 w-3" aria-hidden="true" />{m.label}</Pill>;
}

function DimensionCard({ d }: { d: QualityDimension }) {
  const measurable = d.value_pct !== null;
  const perfect = d.value_pct === 100;
  return (
    <Card as="article" className="flex h-full flex-col p-4 sm:p-5">
      <p className="eyebrow flex items-center gap-1 text-[0.6rem]">{d.label}<InfoTip label={d.label}>{d.definition}</InfoTip></p>
      {measurable ? (
        <>
          <p className="tabular mt-2 text-[1.9rem] leading-none font-semibold tracking-tight">{pctText(d.value_pct)}</p>
          <p className="tabular mt-1.5 text-[0.78rem] text-muted">{d.numerator.toLocaleString("en-IN")} of {d.denominator.toLocaleString("en-IN")}</p>
          <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-white/[0.06]" aria-hidden="true">
            <div className={`h-full rounded-full ${perfect ? "bg-lime-2" : "bg-warn"}`} style={{ width: `${d.value_pct}%` }} />
          </div>
        </>
      ) : (
        <p className="mt-2 flex items-center gap-1.5 text-[1.05rem] font-semibold text-muted"><MinusCircle className="h-4 w-4" aria-hidden="true" />Not measurable</p>
      )}
      {d.note ? <p className="mt-3 text-[0.74rem] leading-relaxed text-faint">{d.note}</p> : null}
    </Card>
  );
}

function TrendChart({ data }: { data: QualityResponse["scorecard"]["trend"] }) {
  const reduced = useReducedMotion();
  const rows = data.map((t, i) => ({ name: `#${i + 1}`, Rejected: t.rows_rejected, "Possible duplicates": t.possible_duplicates,
    "Balance mismatches": t.balance_mismatches, Uncategorised: t.uncategorised }));
  const colors = ["#ff7a6b", "#f5c451", "#8fb8de", "#56604f"];
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="#1e261e" vertical={false} />
        <XAxis dataKey="name" tick={{ fill: "#5f675d", fontSize: 11 }} tickLine={false} axisLine={false} />
        <YAxis allowDecimals={false} width={36} tick={{ fill: "#5f675d", fontSize: 11 }} tickLine={false} axisLine={false} />
        <Tooltip cursor={{ fill: "rgb(255 255 255 / 0.03)" }} contentStyle={{ background: "#151b14", border: "1px solid #2a342a", borderRadius: 12, fontSize: 12 }} />
        <Legend verticalAlign="top" align="right" height={28} formatter={(v) => <span className="text-[0.75rem] text-muted">{v}</span>} />
        {Object.keys(rows[0] ?? {}).filter((k) => k !== "name").map((k, i) => (
          <Bar key={k} dataKey={k} fill={colors[i]} radius={[3, 3, 0, 0]} maxBarSize={18} isAnimationActive={!reduced} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export default function QualityPage() {
  const { ready, mode, version, meta } = useApp();
  const [statementId, setStatementId] = useState<string>("");
  const [issue, setIssue] = useState<string>("");
  const qs = new URLSearchParams();
  if (statementId) qs.set("statement_id", statementId);
  if (issue) qs.set("issue", issue);
  const { data, error, initialLoading, reload } = useApi<QualityResponse>(ready ? `/api/quality${qs.toString() ? `?${qs}` : ""}` : null, [mode, version]);
  const openTransactions = useOpenTransactions();

  if (meta && meta.counts.transactions === 0 && meta.counts.statements === 0) return <NoDataState />;
  if (error && !data) return <ErrorState message={error.message} onRetry={reload} />;
  if (initialLoading || !data) return <div className="space-y-4" role="status" aria-label="Loading"><Skeleton className="h-32" /><Skeleton className="h-72" /></div>;

  const sc = data.scorecard;
  const scopeStatement = data.statements.length === 1 && statementId ? data.statements[0] : null;
  const shownIssues = sc.issues.filter((i) => !issue || i.code === issue);
  const openFor = (status: string) => openTransactions({
    statuses: [status],
    ...(scopeStatement?.statement_period_start ? { start: scopeStatement.statement_period_start, end: scopeStatement.statement_period_end ?? undefined } : {}),
  });

  return (
    <div className="space-y-8">
      {/* ---------- filters */}
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
        <label className="flex flex-col gap-1 text-[0.74rem] text-muted">Import
          <select value={statementId} onChange={(e) => setStatementId(e.target.value)} className={selectCls}>
            <option value="">All imports ({data.all_statements.length})</option>
            {data.all_statements.map((s) => <option key={s.id} value={s.id}>{s.display_name}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-[0.74rem] text-muted">Issue type
          <select value={issue} onChange={(e) => setIssue(e.target.value)} className={selectCls}>
            <option value="">All issue types</option>
            {data.issue_types.map((t) => <option key={t.code} value={t.code}>{t.label}</option>)}
          </select>
        </label>
        <p className="text-[0.74rem] leading-relaxed text-faint sm:ml-auto sm:max-w-sm sm:text-right">
          Every figure is a count from the import validation, or a ratio of two counts. There&apos;s no combined score:
          each dimension measures something different.
        </p>
      </div>

      {/* ---------- dimensions */}
      <section aria-labelledby="dims-title" className="space-y-4">
        <SectionHeader id="dims-title" title="Quality dimensions"
          subtitle={`${sc.scope.statements} import${sc.scope.statements === 1 ? "" : "s"} · ${sc.scope.transactions.toLocaleString("en-IN")} saved transactions. Hover ⓘ for the exact formula.`} />
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {sc.dimensions.map((d) => <li key={d.key}><DimensionCard d={d} /></li>)}
        </ul>
      </section>

      {/* ---------- breakdown */}
      <section aria-labelledby="issues-title" className="space-y-4">
        <SectionHeader id="issues-title" title="Validation findings" subtitle="What was found at import, how many saved rows still carry the flag, and what it means." />
        <div className="flex flex-wrap gap-x-5 gap-y-2 text-[0.74rem] text-faint">
          {(Object.keys(SEVERITY) as Severity[]).map((s) => <span key={s} className="flex items-center gap-2"><SeverityPill s={s} />{SEVERITY[s].text}</span>)}
        </div>
        {shownIssues.length === 0 ? (
          <Card className="flex items-center gap-3 p-5 text-[0.88rem] text-fg/85">
            <CheckCircle2 className="h-5 w-5 text-pos" aria-hidden="true" />
            {issue ? "No findings of this type in the selected imports." : "No validation findings in the selected imports."}
          </Card>
        ) : (
          <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {shownIssues.map((i) => (
              <li key={i.code}>
                <Card as="article" className="flex h-full flex-col p-4 sm:p-5">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <h3 className="text-[0.95rem] font-semibold text-fg">{i.label}</h3>
                    <SeverityPill s={i.severity} />
                  </div>
                  <p className="tabular mt-2 text-[0.82rem] text-muted">
                    {i.count.toLocaleString("en-IN")} {i.unit === "statement" ? `import${i.count === 1 ? "" : "s"}` : `row${i.count === 1 ? "" : "s"}`} at import
                    {i.current_count !== null ? <> · <span className="text-fg/85">{i.current_count.toLocaleString("en-IN")} still flagged</span></> : null}
                    <span className="text-faint"> · {i.dimension}</span>
                  </p>
                  <p className="mt-2 flex-1 text-[0.84rem] leading-relaxed text-fg/80">{i.implication}</p>
                  {i.status_filter && (i.current_count ?? 0) > 0 ? (
                    <button type="button" onClick={() => openFor(i.status_filter!)}
                      className="group mt-3 inline-flex items-center gap-1 self-start rounded-lg px-1.5 py-1 text-[0.8rem] font-medium text-lime hover:bg-lime/10">
                      Show affected transactions <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
                    </button>
                  ) : null}
                </Card>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* ---------- trend */}
      {sc.trend_available && !statementId ? (
        <ChartContainer title="Issues by import" subtitle="One group per import, oldest first. Counts at the time of import."
          table={{ columns: ["Import", "Extracted", "Rejected", "Possible duplicates", "Balance mismatches", "Uncategorised", "Completeness"],
            rows: sc.trend.map((t, n) => [`#${n + 1} ${t.display_name}`, t.rows_extracted, t.rows_rejected, t.possible_duplicates,
              t.balance_mismatches, t.uncategorised, pctText(t.completeness_pct)]) }}>
          <TrendChart data={sc.trend} />
        </ChartContainer>
      ) : (
        <p className="flex items-start gap-2 text-[0.8rem] text-faint"><Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          {statementId ? "Showing one import, so there's no trend." : "A trend across imports appears from your second import. Nothing is simulated before then."}</p>
      )}

      {/* ---------- rejected rows */}
      {data.issues.length ? (
        <section aria-labelledby="rows-title" className="space-y-4">
          <SectionHeader id="rows-title" title={`Rows that weren't imported (${data.issues.length})`}
            subtitle={data.issue_breakdown.map((b) => `${b.label}: ${b.count}`).join(" · ")} />
          <Card className="overflow-x-auto">
            <table className="w-full min-w-[620px] text-left text-[0.82rem]">
              <thead className="border-b border-line text-[0.72rem] text-muted"><tr>
                {["Import", "Page", "Row", "Issue", "Details"].map((h) => <th key={h} scope="col" className="px-4 py-3 font-medium">{h}</th>)}
              </tr></thead>
              <tbody>{data.issues.map((i, n) => (
                <tr key={n} className="border-b border-line/60 last:border-0">
                  <td className="px-4 py-2.5 text-fg">{i.statement}</td>
                  <td className="tabular px-4 py-2.5 text-muted">{i.page ?? "—"}</td>
                  <td className="tabular px-4 py-2.5 text-muted">{i.row_number ?? "—"}</td>
                  <td className="px-4 py-2.5"><span className="flex flex-wrap items-center gap-2"><SeverityPill s={i.severity} /><span className="text-fg/90">{i.label}</span></span></td>
                  <td className="px-4 py-2.5 text-fg/75">{i.reason}</td>
                </tr>))}</tbody>
            </table>
          </Card>
        </section>
      ) : null}

      {/* ---------- per-import reports */}
      <section aria-labelledby="statements-title" className="space-y-4">
        <SectionHeader id="statements-title" title="Import reports"
          subtitle="Extracted = rejected + accepted; accepted = imported + exact duplicates skipped. Flags overlap, so they aren't added up." />
        <Card className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-[0.82rem]">
            <thead className="border-b border-line text-[0.72rem] text-muted"><tr>
              {["Import", "Period", "Extracted", "Rejected", "Accepted", "Duplicates skipped", "Possible dup.", "Balance check", "Reconciliation", "Imported on"].map((h, i) => (
                <th key={h} scope="col" className={`px-4 py-3 font-medium ${i >= 2 && i <= 6 ? "text-right" : ""}`}>{h}</th>))}
            </tr></thead>
            <tbody>{data.statements.map((s) => {
              const r = s.quality_report;
              const rec = r?.reconciliation;
              return (
                <tr key={s.id} className="border-b border-line/60 align-top last:border-0">
                  <td className="px-4 py-3 text-fg">{s.display_name}<span className="block text-[0.7rem] text-faint">{s.parser_name}</span>
                    {s.warnings.length ? <ul className="mt-1 space-y-0.5 text-[0.72rem] text-warn">{s.warnings.map((w) => <li key={w}>{w}</li>)}</ul> : null}</td>
                  <td className="px-4 py-3 whitespace-nowrap text-muted">{fmtDate(s.statement_period_start)} – {fmtDate(s.statement_period_end)}</td>
                  <td className="tabular px-4 py-3 text-right">{s.rows_extracted}</td>
                  <td className="tabular px-4 py-3 text-right">{r ? r.rows_rejected : s.rows_invalid}</td>
                  <td className="tabular px-4 py-3 text-right">{r ? r.rows_accepted : "—"}</td>
                  <td className="tabular px-4 py-3 text-right">{s.rows_skipped_duplicates}</td>
                  <td className="tabular px-4 py-3 text-right">{r ? r.flags.possible_duplicates : "—"}</td>
                  <td className="tabular px-4 py-3">{s.balance_checked_pairs ? `${s.balance_mismatches} of ${s.balance_checked_pairs} pairs off` : "no balance column"}</td>
                  <td className="tabular px-4 py-3">{!rec || !rec.available ? <span className="text-faint">balances not printed</span>
                    : rec.reconciled ? <span className="text-pos">reconciled</span>
                    : <span className="text-neg">off by {inr(Math.abs(rec.difference_paise ?? 0), { decimals: true })}</span>}</td>
                  <td className="px-4 py-3 whitespace-nowrap text-muted">{fmtDate(s.created_at.slice(0, 10))}</td>
                </tr>
              );
            })}</tbody>
          </table>
        </Card>
        <p className="text-[0.74rem] leading-relaxed text-faint">
          These figures describe your data. How accurately the PDF parsers read statements is measured separately on
          synthetic test statements (see docs/PARSER_EVALUATION.md), and no claim is made about real-world parser accuracy.
        </p>
      </section>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <section aria-labelledby="uncat-title" className="space-y-4">
          <SectionHeader id="uncat-title" title="Uncategorised merchants" subtitle="Fix one row and apply it to the whole merchant" />
          <Card className="p-2">
            {data.uncategorized.length === 0 ? <p className="p-3 text-[0.84rem] text-muted">Everything is categorised.</p> : (
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
