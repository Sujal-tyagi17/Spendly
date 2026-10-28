"use client";

import { ArrowDownRight, ArrowRight, ArrowUpRight, CopyX, Scale, Tags } from "lucide-react";
import { NoDataState } from "@/components/app/no-data";
import Link from "next/link";
import { ChartContainer, RankedBars, TrendChart } from "@/components/app/charts";
import { CategoryBadge, TypeBadge } from "@/components/ui/badges";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { Button } from "@/components/ui/button";
import { Card, SectionHeader } from "@/components/ui/card";
import { InsightCard } from "@/components/ui/insight-card";
import { MetricCard } from "@/components/ui/metric-card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import { EMPTY_FILTERS } from "@/lib/api";
import { fmtDate, inr, monthLabel, pct } from "@/lib/format";
import { useFiltered, useOpenTransactions } from "@/lib/hooks";
import { useApp } from "@/lib/store";
import type { Overview } from "@/lib/types";

function OverviewSkeleton() {
  return (
    <div className="space-y-5" role="status" aria-label="Loading overview">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[7.5rem]" />)}</div>
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3"><Skeleton className="h-[360px] xl:col-span-2" /><Skeleton className="h-[360px]" /></div>
    </div>
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

  const t = data.totals;
  const comp = data.comparison;
  const q = data.quality;
  const qualityItems = [
    q.possible_duplicates ? { icon: CopyX, label: `${q.possible_duplicates} possible duplicate${q.possible_duplicates > 1 ? "s" : ""} to review`, link: { statuses: ["possible_duplicate"] } } : null,
    q.uncategorized ? { icon: Tags, label: `${q.uncategorized} uncategorized transaction${q.uncategorized > 1 ? "s" : ""}`, link: { statuses: ["uncategorized"] } } : null,
    q.balance_mismatches ? { icon: Scale, label: `${q.balance_mismatches} running-balance mismatch${q.balance_mismatches > 1 ? "es" : ""} in imported statements`, href: "/app/quality" } : null,
  ].filter(Boolean) as { icon: typeof CopyX; label: string; link?: { statuses: string[] }; href?: string }[];

  const delta = comp && comp.change_pct !== null ? (
    <span className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 font-medium ${comp.change_pct > 0 ? "bg-neg/10 text-neg" : "bg-pos/10 text-pos"}`}>
      {comp.change_pct > 0 ? <ArrowUpRight className="h-3 w-3" aria-hidden="true" /> : <ArrowDownRight className="h-3 w-3" aria-hidden="true" />}
      {pct(comp.change_pct)}<span className="sr-only">{comp.change_pct > 0 ? " increase" : " decrease"}</span>
    </span>
  ) : null;

  return (
    <div className="space-y-5">
      <p className="text-[0.8rem] text-muted">
        Showing {fmtDate(filters.start ?? t.first_date)} – {fmtDate(filters.end ?? t.last_date)} · {t.transaction_count.toLocaleString("en-IN")} transactions
        {data.coverage.start ? <> · covers only the statements you imported</> : null}
      </p>

      {/* ---------- headline metrics */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard emphasis label="Expenditure" value={<AnimatedNumber value={t.expenditure_paise} format={(n) => inr(n)} />}
          delta={delta} note={comp ? `${comp.current.label} vs ${comp.previous.label}` : "spending debits"}
          tip={<>Debits classified as spending. <b>Excludes</b> transfers between your own accounts and credit-card bill payments (the card purchases are the spending). Shown before refunds.</>} />
        <MetricCard label="Income received" value={<AnimatedNumber value={t.income_paise} format={(n) => inr(n)} />}
          note="salary, stipend, interest"
          tip={<>Credits recognised as income. Money from friends is <b>not</b> counted as income. It stays &ldquo;Other&rdquo; until you re-categorize it.</>} />
        <MetricCard label="Net cash flow" value={<AnimatedNumber value={t.net_cash_flow_paise} format={(n) => inr(n, { sign: true })} />}
          note="all money in − all money out"
          tip={<>Every credit minus every debit, <b>excluding</b> transfers between your own accounts. Credit-card bill payments are included because that money really left your account.</>} />
        <MetricCard label="Refunds" value={<AnimatedNumber value={t.refunds_paise} format={(n) => inr(n)} />}
          note={`net expenditure ${inr(t.expenditure_paise - t.refunds_paise)}`}
          tip={<>Credits identified as refunds. Net expenditure = expenditure − refunds.</>} />
      </div>

      {/* ---------- trend + insights */}
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <ChartContainer title="Monthly spending" subtitle="Expenditure by month (before refunds), with income for reference" height={360}
            table={{ columns: ["Month", "Expenditure", "Income", "Change vs previous"],
              rows: data.monthly.map((m) => [monthLabel(m.month_start), inr(m.expenditure_paise), inr(m.income_paise), m.mom_change_pct === null ? "—" : pct(m.mom_change_pct, { sign: true })]) }}>
            <TrendChart data={data.monthly} />
          </ChartContainer>
        </div>
        <Card className="flex flex-col p-4 sm:p-5">
          <SectionHeader title="Key insights" subtitle="Computed from your transactions"
            action={<Link href="/app/insights" className="text-[0.75rem] font-medium text-lime hover:underline">All insights</Link>} />
          <div className="mt-4 flex flex-1 flex-col gap-3">
            {data.insights.slice(0, 2).map((i) => <InsightCard key={i.key} insight={i} compact onOpen={(x) => x.link && openTransactions(x.link)} />)}
          </div>
        </Card>
      </div>

      {/* ---------- breakdowns */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2 xl:grid-cols-3">
        <Card className="p-4 sm:p-5">
          <SectionHeader title="Where it went" subtitle="Expenditure by category. Select one to see its transactions." />
          <div className="mt-4">
            <RankedBars items={data.categories.slice(0, 7).map((c) => ({ label: c.category, value: c.expenditure_paise, share: c.share_pct }))}
              onSelect={(category) => openTransactions({ start: filters.start ?? undefined, end: filters.end ?? undefined, categories: [category], types: ["expense"] })} />
          </div>
        </Card>
        <Card className="p-4 sm:p-5">
          <SectionHeader title="Top merchants" subtitle="Who receives most of your money" />
          <div className="mt-4">
            <RankedBars items={data.top_merchants.map((m) => ({ label: m.merchant, value: m.expenditure_paise, share: m.share_pct, note: `${m.category} · ${m.transaction_count} payments` }))}
              onSelect={(merchant) => openTransactions({ start: filters.start ?? undefined, end: filters.end ?? undefined, merchants: [merchant], types: ["expense"] })} />
          </div>
        </Card>
        <Card className="p-4 sm:p-5 lg:col-span-2 xl:col-span-1">
          <SectionHeader title="Recent transactions"
            action={<Link href="/app/transactions" className="text-[0.75rem] font-medium text-lime hover:underline">View all</Link>} />
          <ul className="mt-3 divide-y divide-line/70">
            {data.recent.slice(0, 7).map((r) => (
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

      {/* ---------- data quality */}
      {qualityItems.length ? (
        <Card className="p-4 sm:p-5">
          <SectionHeader title="Worth reviewing" subtitle="Small fixes that make every number more accurate"
            action={<Link href="/app/quality" className="text-[0.75rem] font-medium text-lime hover:underline">Data quality</Link>} />
          <ul className="mt-3 grid gap-2 md:grid-cols-3">
            {qualityItems.map((item) => {
              const Icon = item.icon;
              const inner = (
                <>
                  <span className="flex items-center gap-2.5 text-[0.84rem] text-fg/90">
                    <Icon className="h-4 w-4 shrink-0 text-warn" aria-hidden="true" />{item.label}
                  </span>
                  <ArrowRight className="h-4 w-4 shrink-0 text-faint transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
                </>
              );
              const cls = "group flex w-full items-center justify-between gap-3 rounded-xl border border-warn/20 bg-warn/[0.04] px-3.5 py-3 text-left transition-colors hover:border-warn/40";
              return (
                <li key={item.label}>
                  {item.href ? <Link href={item.href} className={cls}>{inner}</Link>
                    : <button type="button" className={cls} onClick={() => item.link && openTransactions(item.link)}>{inner}</button>}
                </li>
              );
            })}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}
