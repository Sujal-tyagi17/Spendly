"use client";

import { ArrowDownRight, ArrowUpRight, Info } from "lucide-react";
import { useState } from "react";
import { CashFlowChart, ChartContainer, CumulativeChart, RankedBars, RecurringChart, WeekdayChart } from "@/components/app/charts";
import { NoDataState } from "@/components/app/no-data";
import { Pill } from "@/components/ui/badges";
import { Button } from "@/components/ui/button";
import { Card, SectionHeader } from "@/components/ui/card";
import { MetricCard } from "@/components/ui/metric-card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import { EMPTY_FILTERS } from "@/lib/api";
import { fmtDate, inr, monthLabel, pct } from "@/lib/format";
import { useFiltered, useOpenTransactions } from "@/lib/hooks";
import { useApp } from "@/lib/store";
import type { AnalysisMonth, AnalysisResponse } from "@/lib/types";

/** Plain-English status of a month's comparison (statuses are computed by the SQL). */
function prevStatusLabel(m: AnalysisMonth): string {
  if (!m.is_covered) return "No statement covers this month";
  switch (m.prev_status) {
    case "none": return "First month in view";
    case "not_covered": return "Previous month not in your statements";
    case "zero": return "No spending the month before";
    default: return "";
  }
}

function Change({ paise, pctValue }: { paise: number | null; pctValue: number | null }) {
  if (paise === null) return <span className="text-faint">—</span>;
  const up = paise > 0;
  return (
    <span className={`tabular inline-flex items-center gap-1 ${paise === 0 ? "text-muted" : up ? "text-neg" : "text-pos"}`}>
      {paise !== 0 ? (up ? <ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" /> : <ArrowDownRight className="h-3.5 w-3.5" aria-hidden="true" />) : null}
      {inr(paise, { sign: true })}
      {pctValue !== null ? <span className="text-[0.72rem] opacity-80">({pct(pctValue, { sign: true })})</span> : null}
    </span>
  );
}

const th = "px-3 py-2.5 font-medium whitespace-nowrap";
const td = "px-3 py-2.5 whitespace-nowrap";

export default function AnalysisPage() {
  const { meta, setFilters } = useApp();
  const { data, error, initialLoading, reload } = useFiltered<AnalysisResponse>("/api/analysis");
  const openTransactions = useOpenTransactions();
  const [showAllMerchants, setShowAllMerchants] = useState(false);

  if (meta && meta.counts.transactions === 0) return <NoDataState />;
  if (error && !data) return <ErrorState message={error.message} onRetry={reload} />;
  if (initialLoading || !data) {
    return <div className="space-y-5" role="status" aria-label="Loading analysis"><Skeleton className="h-28" /><Skeleton className="h-80" /><Skeleton className="h-80" /></div>;
  }
  if (data.totals.transaction_count === 0) {
    return <EmptyState title="No transactions match these filters" action={<Button onClick={() => setFilters(EMPTY_FILTERS)}>Clear filters</Button>}>Widen the date range or remove filters.</EmptyState>;
  }

  const t = data.totals;
  const conc = data.concentration;
  const all = data.weekend[0];
  const lastMonth = data.monthly[data.monthly.length - 1];
  const latestCats = data.category_monthly.filter((c) => c.month_start === lastMonth?.month_start && c.prev_expenditure_paise !== null && c.change_paise !== 0)
    .sort((a, b) => Math.abs(b.change_paise ?? 0) - Math.abs(a.change_paise ?? 0)).slice(0, 6);
  const merchants = showAllMerchants ? data.merchants : data.merchants.slice(0, 10);
  const rec = data.recurring;

  return (
    <div className="space-y-10">
      <p className="max-w-3xl text-[0.88rem] leading-relaxed text-muted">
        A deeper look at {fmtDate(data.range.start)} – {fmtDate(data.range.end)}. Every figure is calculated by the SQL queries in the
        project&apos;s <code className="font-mono text-[0.8rem] text-fg/80">sql/</code> folder using one shared definition of spending, income, refunds and transfers.
        These are descriptions of your data, not explanations of why it happened.
      </p>

      {/* ------------------------------------------------ cash flow */}
      <section aria-labelledby="cf-title" className="space-y-4">
        <SectionHeader id="cf-title" title="Cash flow" subtitle="Money in vs money out. Transfers between your own accounts are excluded." />
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <MetricCard label="Income" value={inr(t.income_paise)} note="salary, stipend, interest" tip={data.definitions.is_income} />
          <MetricCard label="Expenditure" value={inr(t.expenditure_paise)} note="spending debits" tip={data.definitions.is_expense} />
          <MetricCard label="Refunds" value={inr(t.refunds_paise)} note="money returned" tip={data.definitions.is_refund} />
          <MetricCard emphasis label="Net cash flow" value={inr(t.net_cash_flow_paise, { sign: true })} note="credits − debits" tip={data.definitions.cash_flow_paise} />
        </div>
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
          <ChartContainer title="Income and expenditure by month" height={280}
            table={{ columns: ["Month", "Income", "Expenditure", "Refunds", "Net cash flow"],
              rows: data.monthly.map((m) => [monthLabel(m.month_start), inr(m.income_paise), inr(m.expenditure_paise), inr(m.refunds_paise), inr(m.net_cash_flow_paise, { sign: true })]) }}>
            <CashFlowChart data={data.monthly} />
          </ChartContainer>
          <ChartContainer title="Running net cash flow" subtitle="Cumulative total across the months in view" height={280}
            table={{ columns: ["Month", "Net cash flow", "Running total"],
              rows: data.monthly.map((m) => [monthLabel(m.month_start), inr(m.net_cash_flow_paise, { sign: true }), inr(m.cumulative_net_cash_flow_paise, { sign: true })]) }}>
            <CumulativeChart data={data.monthly} />
          </ChartContainer>
        </div>
      </section>

      {/* ------------------------------------------------ month over month */}
      <section aria-labelledby="mom-title" className="space-y-4">
        <SectionHeader id="mom-title" title="Month over month"
          subtitle="A month with no statement is shown as missing, never as zero spending, so it can't fake a 100% drop." />
        <Card className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-[0.84rem]">
            <thead className="border-b border-line text-[0.72rem] text-muted"><tr>
              <th scope="col" className={th}>Month</th><th scope="col" className={`${th} text-right`}>Expenditure</th>
              <th scope="col" className={`${th} text-right`}>Previous month</th><th scope="col" className={th}>Change</th>
              <th scope="col" className={th}>Note</th></tr></thead>
            <tbody>{data.monthly.map((m) => (
              <tr key={m.month_start} className="border-b border-line/60 last:border-0">
                <td className={`${td} text-fg`}>{monthLabel(m.month_start)}{!m.is_full_month && m.is_covered ? <span className="ml-2"><Pill>partial</Pill></span> : null}</td>
                <td className={`${td} tabular text-right ${m.is_covered ? "text-fg" : "text-faint"}`}>{m.is_covered ? inr(m.expenditure_paise) : "—"}</td>
                <td className={`${td} tabular text-right text-muted`}>{m.prev_expenditure_paise === null || m.prev_status === "not_covered" ? "—" : inr(m.prev_expenditure_paise)}</td>
                <td className={td}><Change paise={m.expenditure_change_paise} pctValue={m.mom_change_pct} /></td>
                <td className={`${td} text-[0.76rem] text-faint`}>{prevStatusLabel(m)}</td>
              </tr>))}</tbody>
          </table>
        </Card>
      </section>

      {/* ------------------------------------------------ categories */}
      <section aria-labelledby="cat-title" className="space-y-4">
        <SectionHeader id="cat-title" title="Category contribution" subtitle="Share of expenditure, ranked, and what moved in the latest month" />
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-[1fr_1.1fr]">
          <Card className="p-4 sm:p-5">
            <SectionHeader title="Share of expenditure" subtitle="Select a category to see its transactions" level={3} />
            <div className="mt-4">
              <RankedBars items={data.categories.map((c) => ({ label: c.category, value: c.expenditure_paise, share: c.share_pct, note: `#${c.spend_rank ?? ""} · ${c.transaction_count} payments · avg ${inr(c.avg_transaction_paise)}` }))}
                onSelect={(category) => openTransactions({ start: data.range.start ?? undefined, end: data.range.end ?? undefined, categories: [category], types: ["expense"] })} />
            </div>
          </Card>
          <Card className="p-4 sm:p-5">
            <SectionHeader title={lastMonth ? `What moved in ${monthLabel(lastMonth.month_start)}` : "Latest month"} level={3}
              subtitle="Each category's change and its share of the month's total change" />
            {latestCats.length === 0 ? <p className="mt-4 text-[0.84rem] text-muted">No earlier month to compare with.</p> : (
              <div className="mt-3 overflow-x-auto">
                <table className="w-full min-w-[440px] text-left text-[0.82rem]">
                  <thead className="text-[0.7rem] text-muted"><tr>
                    <th scope="col" className={th}>Category</th><th scope="col" className={th}>Change</th>
                    <th scope="col" className={`${th} text-right`}>Share of change</th><th scope="col" className={`${th} text-right`}>Rank</th></tr></thead>
                  <tbody>{latestCats.map((c) => (
                    <tr key={c.category} className="border-t border-line/60">
                      <td className={`${td} text-fg`}>{c.category}</td>
                      <td className={td}><Change paise={c.change_paise} pctValue={c.change_pct} /></td>
                      <td className={`${td} tabular text-right text-muted`}>{c.share_of_change_pct === null ? "—" : `${c.share_of_change_pct.toFixed(0)}%`}</td>
                      <td className={`${td} tabular text-right text-muted`}>#{c.rank_in_month}</td>
                    </tr>))}</tbody>
                </table>
                <p className="mt-3 text-[0.72rem] leading-relaxed text-faint">
                  Share of change is signed: a category moving in the opposite direction to the total gets a negative share.
                </p>
              </div>
            )}
          </Card>
        </div>
      </section>

      {/* ------------------------------------------------ merchants */}
      <section aria-labelledby="mer-title" className="space-y-4">
        <SectionHeader id="mer-title" title="Merchant ranking" subtitle={`${data.merchant_count} merchants received spending in this period`}
          action={data.merchants.length > 10 ? <Button size="sm" variant="ghost" onClick={() => setShowAllMerchants((v) => !v)}>{showAllMerchants ? "Show top 10" : `Show top ${data.merchants.length}`}</Button> : null} />
        <Card className="overflow-x-auto">
          <table className="w-full min-w-[880px] text-left text-[0.82rem]">
            <caption className="sr-only">Merchants ranked by expenditure</caption>
            <thead className="border-b border-line text-[0.7rem] text-muted"><tr>
              {["#", "Merchant", "Payments", "Total", "Average", "Median", "Share", "Cumulative", "Active months"].map((h, i) => (
                <th key={h} scope="col" className={`${th} ${i >= 2 ? "text-right" : ""}`}>{h}</th>))}
            </tr></thead>
            <tbody>{merchants.map((m) => (
              <tr key={m.merchant} className="border-b border-line/60 transition-colors last:border-0 hover:bg-white/[0.02]">
                <td className={`${td} tabular text-faint`}>{m.spend_rank}</td>
                <td className={td}>
                  <button type="button" onClick={() => openTransactions({ start: data.range.start ?? undefined, end: data.range.end ?? undefined, merchants: [m.merchant], types: ["expense"] })}
                    className="text-left text-fg hover:text-lime hover:underline">{m.merchant}</button>
                  <span className="block text-[0.7rem] text-faint">{m.category}</span>
                </td>
                <td className={`${td} tabular text-right`}>{m.transaction_count}</td>
                <td className={`${td} tabular text-right text-fg`}>{inr(m.expenditure_paise)}</td>
                <td className={`${td} tabular text-right text-muted`}>{inr(m.avg_transaction_paise)}</td>
                <td className={`${td} tabular text-right text-muted`}>{inr(m.median_transaction_paise)}</td>
                <td className={`${td} tabular text-right`}>{m.share_pct.toFixed(1)}%</td>
                <td className={`${td} tabular text-right text-muted`}>{m.cumulative_share_pct.toFixed(1)}%</td>
                <td className={`${td} tabular text-right text-muted`}>{m.active_months}</td>
              </tr>))}</tbody>
          </table>
        </Card>
        <p className="text-[0.75rem] leading-relaxed text-faint">
          When the average is far above the median, a few large payments are pulling it up. The median shows a &ldquo;normal&rdquo; payment.
        </p>
      </section>

      {/* ------------------------------------------------ concentration */}
      <section aria-labelledby="conc-title" className="space-y-4">
        <SectionHeader id="conc-title" title="Spending concentration" subtitle="Is your spending spread out, or dominated by a few merchants?" />
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <MetricCard label="Top merchant" value={conc.top_1_share_pct === null ? "—" : `${conc.top_1_share_pct.toFixed(1)}%`} note={conc.top_merchant ?? ""} />
          <MetricCard label="Top 5 merchants" value={conc.top_5_share_pct === null ? "—" : `${conc.top_5_share_pct.toFixed(1)}%`} note={`of ${conc.merchant_count} merchants`} />
          <MetricCard label="Top 10 merchants" value={conc.top_10_share_pct === null ? "—" : `${conc.top_10_share_pct.toFixed(1)}%`} note="share of expenditure" />
          <MetricCard label="Concentration (HHI)" value={conc.hhi === null ? "—" : Math.round(conc.hhi).toLocaleString("en-IN")}
            note={conc.hhi_level ? `${conc.hhi_level} concentration` : ""}
            tip="Herfindahl–Hirschman index: the sum of each merchant's squared % share, from near 0 (spread out) to 10,000 (one merchant). Bands borrowed from competition analysis: under 1,500 low, 1,500–2,500 moderate, above 2,500 high." />
        </div>
        <Card className="flex gap-3 p-4 text-[0.82rem] leading-relaxed text-muted">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-lime-2" aria-hidden="true" />
          <p>
            Largest category: <b className="font-medium text-fg">{conc.top_category ?? "—"}</b> ({conc.top_category_share_pct?.toFixed(1) ?? "—"}% of expenditure).
            Largest merchant: <b className="font-medium text-fg">{conc.top_merchant ?? "—"}</b> ({conc.top_1_share_pct?.toFixed(1) ?? "—"}%).
            High concentration isn&apos;t good or bad in itself. One large fixed cost, such as rent, can dominate it. It also depends on how merchant
            names were grouped (a local shop with two spellings counts twice), and with few merchants the top-5/top-10 shares are close to 100% automatically.
          </p>
        </Card>
      </section>

      {/* ------------------------------------------------ weekday / weekend */}
      <section aria-labelledby="wk-title" className="space-y-4">
        <SectionHeader id="wk-title" title="Weekdays vs weekends"
          subtitle={`${all?.weekday_days ?? 0} weekdays and ${all?.weekend_days ?? 0} weekend days in this period. Per-day figures make the comparison fair.`} />
        {all ? (
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <MetricCard label="Weekday spend / day" value={inr(all.weekday_per_day_paise)} note={`${inr(all.weekday_paise)} total`} />
            <MetricCard label="Weekend spend / day" value={inr(all.weekend_per_day_paise)} note={`${inr(all.weekend_paise)} total`} />
            <MetricCard label="Avg weekday payment" value={inr(all.weekday_avg_txn_paise)} note={`${all.weekday_txns} payments`} />
            <MetricCard label="Avg weekend payment" value={inr(all.weekend_avg_txn_paise)} note={`${all.weekend_txns} payments`} />
          </div>
        ) : null}
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-[1fr_1.1fr]">
          <ChartContainer title="Spending by day of week" subtitle="Total expenditure" height={260}
            table={{ columns: ["Day", "Spent", "Payments", "Average"], rows: data.weekday.map((w) => [w.weekday_name, inr(w.expenditure_paise), w.transaction_count, inr(w.avg_transaction_paise)]) }}>
            <WeekdayChart data={data.weekday} />
          </ChartContainer>
          <Card className="overflow-x-auto p-4 sm:p-5">
            <SectionHeader title="By category" subtitle="Share of each category's spending that happened on weekends" level={3} />
            <table className="mt-3 w-full min-w-[420px] text-left text-[0.82rem]">
              <thead className="text-[0.7rem] text-muted"><tr>
                <th scope="col" className={th}>Category</th><th scope="col" className={`${th} text-right`}>Weekday</th>
                <th scope="col" className={`${th} text-right`}>Weekend</th><th scope="col" className={`${th} text-right`}>Weekend share</th></tr></thead>
              <tbody>{data.weekend.slice(1).map((w) => (
                <tr key={w.scope} className="border-t border-line/60">
                  <td className={`${td} text-fg`}>{w.scope}</td>
                  <td className={`${td} tabular text-right text-muted`}>{inr(w.weekday_paise)}</td>
                  <td className={`${td} tabular text-right text-muted`}>{inr(w.weekend_paise)}</td>
                  <td className={`${td} tabular text-right`}>{w.weekend_share_pct === null ? "—" : `${w.weekend_share_pct.toFixed(0)}%`}</td>
                </tr>))}</tbody>
            </table>
            <p className="mt-3 text-[0.72rem] text-faint">Weekends are 2 of 7 days (about 29%), so a share near 29% means no weekend tilt. This describes your data. It doesn&apos;t explain why.</p>
          </Card>
        </div>
      </section>

      {/* ------------------------------------------------ recurring */}
      <section aria-labelledby="rec-title" className="space-y-4">
        <SectionHeader id="rec-title" title="Recurring commitments"
          subtitle="Actual payments to confirmed or high-confidence recurring merchants, each counted once" />
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <MetricCard emphasis label="Share of expenditure" value={rec.share_of_expenditure_pct === null ? "—" : `${rec.share_of_expenditure_pct.toFixed(1)}%`} note={`${rec.merchants.length} recurring merchants`} />
          <MetricCard label="Paid to recurring" value={inr(rec.actual_recurring_paise)} note={`of ${inr(rec.total_expenditure_paise)} spent`} />
          <MetricCard label="Est. per month" value={inr(rec.estimated_monthly_paise)} note="estimate from typical amounts" />
          <MetricCard label="Est. per year" value={inr(rec.estimated_annual_paise)} note="monthly estimate × 12" />
        </div>
        {rec.monthly.length ? (
          <ChartContainer title="Recurring vs other spending" subtitle={rec.merchants.join(" · ")} height={260}
            table={{ columns: ["Month", "Recurring", "Total expenditure", "Recurring share"],
              rows: rec.monthly.map((m) => [monthLabel(m.month_start), inr(m.recurring_paise), inr(m.expenditure_paise), m.share_pct === null ? "—" : `${m.share_pct.toFixed(1)}%`]) }}>
            <RecurringChart data={rec.monthly} />
          </ChartContainer>
        ) : <EmptyState title="No active recurring payments in this view">Recurring detection needs at least three regular payments to the same merchant.</EmptyState>}
      </section>
    </div>
  );
}
