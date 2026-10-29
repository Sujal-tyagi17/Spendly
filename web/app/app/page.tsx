"use client";

import { ArrowDownRight, ArrowRight, ArrowUpRight, CopyX, FileDown, Info, ScanSearch, Tags } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { ChartContainer, RankedBars, TrendChart } from "@/components/app/charts";
import { NoDataState } from "@/components/app/no-data";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { CategoryBadge, Pill, TypeBadge } from "@/components/ui/badges";
import { Button } from "@/components/ui/button";
import { Card, SectionHeader } from "@/components/ui/card";
import { MetricCard } from "@/components/ui/metric-card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import { ApiError, EMPTY_FILTERS, downloadFile, filtersToQuery } from "@/lib/api";
import { fmtDate, inr, monthLabel, pct } from "@/lib/format";
import { useFiltered, useOpenTransactions } from "@/lib/hooks";
import { useApp } from "@/lib/store";
import type { ChangeStory, Overview } from "@/lib/types";

function OverviewSkeleton() {
  return (
    <div className="space-y-5" role="status" aria-label="Loading overview">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[7.5rem]" />)}</div>
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3"><Skeleton className="h-[360px] xl:col-span-2" /><Skeleton className="h-[360px]" /></div>
    </div>
  );
}

const monthEnd = (start: string) => {
  const d = new Date(`${start.slice(0, 7)}-01T00:00:00Z`);
  d.setUTCMonth(d.getUTCMonth() + 1);
  d.setUTCDate(0);
  return d.toISOString().slice(0, 10);
};

/** Downloads the backend-generated PDF for one month, with the current non-date filters. */
function ReportButton({ months }: { months: string[] }) {
  const { filters, mode, notify } = useApp();
  const [month, setMonth] = useState(months[months.length - 1] ?? "");
  const [busy, setBusy] = useState(false);
  if (!months.length) return null;
  const download = async () => {
    setBusy(true);
    try {
      const q = filtersToQuery({ ...filters, start: null, end: null }, { month });
      await downloadFile(`/api/report/monthly.pdf${q}`, `spendly-report-${month}${mode === "demo" ? "-demo" : ""}.pdf`);
      notify(`Report for ${monthLabel(`${month}-01`)} downloaded.`);
    } catch (e) {
      notify(e instanceof ApiError ? e.message : "Couldn't create the report.", "error");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="flex items-center gap-2">
      <label className="sr-only" htmlFor="report-month">Report month</label>
      <select id="report-month" value={month} onChange={(e) => setMonth(e.target.value)}
        className="h-9 rounded-lg border border-line bg-ink-2 px-2.5 text-[0.8rem] text-fg">
        {[...months].reverse().map((m) => <option key={m} value={m}>{monthLabel(`${m}-01`)}</option>)}
      </select>
      <Button size="sm" onClick={download} loading={busy}><FileDown className="h-3.5 w-3.5" aria-hidden="true" />Monthly report (PDF)</Button>
    </div>
  );
}

function StoryCard({ story }: { story: ChangeStory }) {
  return (
    <Card className="flex flex-col p-4 sm:p-5">
      <SectionHeader title="Why spending changed" subtitle={story.current_label ? `${story.current_label} vs ${story.previous_label}` : "Latest month vs the one before"}
        action={<Link href="/app/insights" className="text-[0.75rem] font-medium text-lime hover:underline">More insights</Link>} />
      {story.available && story.headline ? (
        <div className="mt-3 flex flex-1 flex-col gap-3 text-[0.84rem] leading-relaxed">
          <p className="text-fg/95">{story.headline}</p>
          <ul className="space-y-2.5">
            {story.points.map((p) => (
              <li key={p.key} className="rounded-xl border border-line bg-ink-2/60 px-3 py-2.5">
                <p className="text-[0.7rem] font-medium tracking-wide text-faint uppercase">{p.title}</p>
                <p className="mt-0.5 text-fg/85">{p.text}</p>
              </li>
            ))}
          </ul>
          <div className="mt-auto space-y-1 pt-1">{story.caveats.map((c) => <p key={c} className="flex gap-1.5 text-[0.72rem] text-faint"><Info className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />{c}</p>)}</div>
        </div>
      ) : (
        <p className="mt-3 text-[0.84rem] text-muted">{story.caveats[0] ?? "Not enough data for a reliable comparison."}</p>
      )}
    </Card>
  );
}

export default function OverviewPage() {
  const { meta, setFilters, filters } = useApp();
  const { data, error, initialLoading, reload } = useFiltered<Overview>("/api/overview");
  const openTransactions = useOpenTransactions();

  if (error && !data) return <ErrorState message={error.message} onRetry={reload} />;
  if (initialLoading || !data) return <OverviewSkeleton />;
  if (meta && meta.counts.transactions === 0) return <NoDataState />;
  if (data.totals.transaction_count === 0) {
    return (
      <EmptyState title="No transactions match these filters"
        action={<Button onClick={() => setFilters(EMPTY_FILTERS)}>Clear filters</Button>}>
        Try a wider date range or remove some filters.
      </EmptyState>
    );
  }

  const x = data.executive;
  const mom = x.month_over_month;
  const t = data.totals;
  const q = data.quality;
  const wk = data.weekend[0];
  const months = data.monthly.filter((m) => m.is_covered).map((m) => m.month_start.slice(0, 7));
  const view = { start: filters.start ?? undefined, end: filters.end ?? undefined };


  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-[0.8rem] text-muted">
          Showing {fmtDate(filters.start ?? t.first_date)} – {fmtDate(filters.end ?? t.last_date)} · {t.transaction_count.toLocaleString("en-IN")} transactions
          {data.coverage.start ? <> · imported statements only</> : null}
        </p>
        <ReportButton key={months.join()} months={months} />
      </div>

      {/* ---------- executive KPIs: every value is computed by the API (src/kpis.py) */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard emphasis label="Expenditure" value={<AnimatedNumber value={x.expenditure_paise} format={(n) => inr(n)} />}
          note={`before refunds of ${inr(x.refunds_paise)}`}
          tip={<>Debits classified as spending. <b>Excludes</b> transfers between your own accounts and credit-card bill payments. Shown before refunds.</>} />
        <MetricCard label="Income" value={<AnimatedNumber value={x.income_paise} format={(n) => inr(n)} />}
          note="salary, stipend, interest"
          tip={<>Credits recognised as income. Money from friends is <b>not</b> counted as income until you re-categorise it.</>} />
        <MetricCard label="Net cash flow" value={<AnimatedNumber value={x.net_cash_flow_paise} format={(n) => inr(n, { sign: true })} />}
          note="all money in − all money out"
          tip={<>Every credit minus every debit, <b>excluding</b> transfers between your own accounts.</>} />
        <MetricCard label="Average month" value={x.average_monthly_expenditure.value_paise === null ? "n/a" : inr(x.average_monthly_expenditure.value_paise)}
          note={x.average_monthly_expenditure.months ? `expenditure, ${x.average_monthly_expenditure.months} complete month${x.average_monthly_expenditure.months === 1 ? "" : "s"}` : "no complete month in view"}
          tip={<>Mean expenditure of months fully covered by your statements <b>and</b> fully inside the date filter. Partial months are left out, not scaled up.</>} />
        <MetricCard label="Change vs previous month"
          value={mom && mom.change_pct !== null ? (
            <span className={`inline-flex items-center gap-1 ${mom.change_pct > 0 ? "text-neg" : "text-pos"}`}>
              {mom.change_pct > 0 ? <ArrowUpRight className="h-6 w-6" aria-hidden="true" /> : <ArrowDownRight className="h-6 w-6" aria-hidden="true" />}
              {pct(mom.change_pct, { sign: true })}<span className="sr-only">{mom.change_pct > 0 ? " increase" : " decrease"}</span>
            </span>) : "n/a"}
          note={mom ? `${mom.current_label} vs ${mom.previous_label}` : "no earlier month to compare"}
          tip={<>Expenditure in the latest month in view vs the month before. A partial month is compared with the same days of the previous month. n/a when the previous month had no spending.</>} />
        <MetricCard label="Recurring (estimate)" value={inr(x.recurring.estimated_monthly_paise)}
          note={`${x.recurring.active_count} active recurring payment${x.recurring.active_count === 1 ? "" : "s"} / month`}
          tip={<>Typical monthly cost of confirmed and high-confidence recurring payments that are still active. An estimate, not a bill.</>} />
        <MetricCard label="Budget used" value={x.budget ? (x.budget.utilisation_pct === null ? "n/a" : `${x.budget.utilisation_pct.toFixed(1)}%`) : "No budget"}
          note={x.budget ? `${monthLabel(x.budget.month)}: ${inr(x.budget.actual_paise)} of ${inr(x.budget.budget_paise)}${x.budget.is_full_month ? "" : " (so far)"}` : <Link href="/app/budgets" className="text-lime hover:underline">Set a budget</Link>}
          tip={<>Latest month in view: expenditure ÷ overall budget × 100 (or ÷ the sum of category budgets if there is no overall budget).</>}
          delta={x.budget ? <Pill tone={x.budget.status === "over" ? "neg" : x.budget.status === "within" ? "pos" : "warn"}>{x.budget.status.replace("_", " ")}</Pill> : null} />
        <MetricCard label="Unusual payments" value={String(data.anomaly_count)}
          note={<Link href="/app/insights#unusual-title" className="text-lime hover:underline">Review on Insights</Link>}
          tip={<>Payments far above your earlier payments at the same merchant or category (robust z-score). Unusual isn&apos;t the same as fraud.</>} />
      </div>

      {/* ---------- trend + story */}
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <ChartContainer title="Monthly spending" subtitle="Expenditure by month (before refunds), with income for reference. Select a month to see its transactions." height={420}
            table={{ columns: ["Month", "Expenditure", "Income", "Change vs previous", "Coverage"],
              rows: data.monthly.map((m) => [monthLabel(m.month_start), inr(m.expenditure_paise), inr(m.income_paise),
                m.mom_change_pct === null ? "—" : pct(m.mom_change_pct, { sign: true }), !m.is_covered ? "not covered" : m.is_full_month ? "full" : "partial"]) }}>
            <TrendChart data={data.monthly} onSelectMonth={(m) => openTransactions({ start: m.slice(0, 10), end: monthEnd(m), types: ["expense"] })} />
          </ChartContainer>
        </div>
        <StoryCard story={data.story} />
      </div>

      {/* ---------- breakdowns */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2 xl:grid-cols-3">
        <Card className="p-4 sm:p-5">
          <SectionHeader title="Where it went" subtitle="Expenditure by category. Select one to see its transactions." />
          <div className="mt-4">
            <RankedBars items={data.categories.slice(0, 7).map((c) => ({ label: c.category, value: c.expenditure_paise, share: c.share_pct }))}
              onSelect={(category) => openTransactions({ ...view, categories: [category], types: ["expense"] })} />
          </div>
        </Card>
        <Card className="p-4 sm:p-5">
          <SectionHeader title="Top merchants" subtitle="Who receives most of your money" />
          <div className="mt-4">
            <RankedBars items={data.top_merchants.map((m) => ({ label: m.merchant, value: m.expenditure_paise, share: m.share_pct, note: `${m.category} · ${m.transaction_count} payments` }))}
              onSelect={(merchant) => openTransactions({ ...view, merchants: [merchant], types: ["expense"] })} />
          </div>
        </Card>
        <Card className="p-4 sm:p-5 lg:col-span-2 xl:col-span-1">
          <SectionHeader title="Weekdays vs weekends" subtitle="Spend per calendar day, so 5 weekdays and 2 weekend days compare fairly"
            action={<Link href="/app/analysis" className="text-[0.75rem] font-medium text-lime hover:underline">Details</Link>} />
          {wk && (wk.weekday_per_day_paise !== null || wk.weekend_per_day_paise !== null) ? (
            <RankedBars items={[
              { label: "Weekday, per day", value: wk.weekday_per_day_paise ?? 0, note: `${inr(wk.weekday_paise)} over ${wk.weekday_days} days · ${wk.weekday_txns} payments` },
              { label: "Weekend, per day", value: wk.weekend_per_day_paise ?? 0, note: `${inr(wk.weekend_paise)} over ${wk.weekend_days} days · ${wk.weekend_txns} payments` },
            ]} />
          ) : <p className="mt-4 text-[0.84rem] text-muted">No spending in this view.</p>}
          {wk?.weekend_share_pct !== null && wk?.weekend_share_pct !== undefined ? (
            <p className="mt-3 text-[0.74rem] text-faint">{wk.weekend_share_pct.toFixed(1)}% of expenditure happened on weekends.</p>
          ) : null}
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card className="p-4 sm:p-5">
          <SectionHeader title="Data quality" subtitle="How far these numbers can be trusted (whole account)"
            action={<Link href="/app/quality" className="text-[0.75rem] font-medium text-lime hover:underline">Scorecard</Link>} />
          <ul className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
            {data.scorecard.map((d) => (
              <li key={d.key} className="rounded-xl border border-line bg-ink-2/60 px-3 py-2.5">
                <p className="truncate text-[0.68rem] text-faint" title={d.label}>{d.label}</p>
                <p className={`tabular mt-0.5 text-[1.05rem] font-semibold ${d.value_pct === null ? "text-muted" : d.value_pct === 100 ? "text-fg" : "text-warn"}`}>
                  {d.value_pct === null ? "n/a" : `${d.value_pct.toFixed(1)}%`}</p>
              </li>
            ))}
          </ul>
          <div className="mt-3 flex flex-wrap gap-2">
            {q.possible_duplicates ? <Button size="sm" variant="ghost" onClick={() => openTransactions({ statuses: ["possible_duplicate"] })}><CopyX className="h-3.5 w-3.5 text-warn" aria-hidden="true" />{q.possible_duplicates} possible duplicate{q.possible_duplicates > 1 ? "s" : ""}</Button> : null}
            {q.uncategorized ? <Button size="sm" variant="ghost" onClick={() => openTransactions({ statuses: ["uncategorized"] })}><Tags className="h-3.5 w-3.5 text-warn" aria-hidden="true" />{q.uncategorized} uncategorised</Button> : null}
            {data.anomaly_count ? <Link href="/app/insights#unusual-title" className="inline-flex h-8 items-center gap-1.5 rounded-lg px-3 text-[0.8rem] font-medium text-muted hover:bg-white/[0.05] hover:text-fg"><ScanSearch className="h-3.5 w-3.5 text-warn" aria-hidden="true" />{data.anomaly_count} unusual</Link> : null}
          </div>
        </Card>
        <Card className="p-4 sm:p-5">
          <SectionHeader title="Recent transactions"
            action={<Link href="/app/transactions" className="text-[0.75rem] font-medium text-lime hover:underline">View all <ArrowRight className="inline h-3 w-3" aria-hidden="true" /></Link>} />
          <ul className="mt-3 divide-y divide-line/70">
            {data.recent.slice(0, 6).map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <p className="truncate text-[0.86rem] text-fg">{r.merchant}</p>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[0.7rem] text-faint">
                    {fmtDate(r.date, { year: false })}
                    {r.type === "expense" ? <CategoryBadge category={r.category} /> : <TypeBadge type={r.type} />}
                  </div>
                </div>
                <span className={`tabular shrink-0 text-[0.88rem] ${r.direction === "credit" ? "text-pos" : "text-fg/85"}`}>
                  {inr(r.direction === "credit" ? r.amount_paise : -r.amount_paise, { sign: true })}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
