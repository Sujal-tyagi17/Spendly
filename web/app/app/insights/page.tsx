"use client";

import { ArrowDownRight, ArrowRight, ArrowUpRight } from "lucide-react";
import { useState } from "react";
import { ChartContainer, CompareChart, WeekdayChart } from "@/components/app/charts";
import { AnomalySection } from "@/components/app/anomalies";
import { NoDataState } from "@/components/app/no-data";
import { Card, SectionHeader } from "@/components/ui/card";
import { InsightCard } from "@/components/ui/insight-card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import { ApiError, apiSend } from "@/lib/api";
import { fmtDate, inr, pct } from "@/lib/format";
import { useFiltered, useOpenTransactions } from "@/lib/hooks";
import { useApp } from "@/lib/store";
import type { InsightsResponse } from "@/lib/types";

export default function InsightsPage() {
  const { meta, refresh, notify } = useApp();
  const { data, error, initialLoading, reload } = useFiltered<InsightsResponse>("/api/insights");
  const openTransactions = useOpenTransactions();
  const [busyId, setBusyId] = useState<number | null>(null);

  if (meta && meta.counts.transactions === 0) return <NoDataState />;
  if (error && !data) return <ErrorState message={error.message} onRetry={reload} />;
  if (initialLoading || !data) {
    return <div className="space-y-5" role="status" aria-label="Loading insights"><Skeleton className="h-40" /><div className="grid grid-cols-1 gap-4 md:grid-cols-3"><Skeleton className="h-44" /><Skeleton className="h-44" /><Skeleton className="h-44" /></div></div>;
  }

  const comp = data.comparison;
  const cards = data.insights.filter((i) => i.key !== "overall_change" && i.key !== "unusual");
  const more = data.merchant_changes.filter((m) => m.change_paise > 0).sort((a, b) => b.change_paise - a.change_paise).slice(0, 5);
  const less = data.merchant_changes.filter((m) => m.change_paise < 0).sort((a, b) => a.change_paise - b.change_paise).slice(0, 5);

  const review = async (id: number, status: "dismissed" | "expected") => {
    setBusyId(id);
    try {
      await apiSend(`/api/anomalies/${id}`, "POST", { status });
      notify(status === "expected" ? "Marked as expected." : "Alert dismissed.");
      refresh();
    } catch (e) {
      notify(e instanceof ApiError ? e.message : "Couldn't update the alert.", "error");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-8">
      {/* ---------- headline */}
      <section aria-labelledby="change-title">
        {comp && data.headline ? (
          <Card className="relative overflow-hidden p-5 sm:p-7">
            <div aria-hidden="true" className="pointer-events-none absolute -top-24 -right-24 h-64 w-64 rounded-full bg-lime/[0.06] blur-3xl" />
            <p className="eyebrow">What changed · {comp.current.label} vs {comp.previous.label}</p>
            <h2 id="change-title" className="mt-3 max-w-3xl text-balance text-[1.35rem] leading-snug font-semibold tracking-tight text-fg sm:text-[1.65rem]">
              {data.headline.text}
            </h2>
            <dl className="mt-6 grid max-w-2xl grid-cols-3 gap-4 border-t border-line pt-5">
              <div><dt className="eyebrow text-[0.6rem]">{comp.previous.label}</dt><dd className="tabular mt-1 text-lg font-semibold">{inr(comp.previous_paise)}</dd></div>
              <div><dt className="eyebrow text-[0.6rem]">{comp.current.label}</dt><dd className="tabular mt-1 text-lg font-semibold">{inr(comp.current_paise)}</dd></div>
              <div><dt className="eyebrow text-[0.6rem]">Change</dt>
                <dd className={`tabular mt-1 flex items-center gap-1 text-lg font-semibold ${comp.change_paise > 0 ? "text-neg" : comp.change_paise < 0 ? "text-pos" : "text-fg"}`}>
                  {comp.change_paise > 0 ? <ArrowUpRight className="h-4 w-4" aria-hidden="true" /> : comp.change_paise < 0 ? <ArrowDownRight className="h-4 w-4" aria-hidden="true" /> : null}
                  {comp.change_pct === null ? "New" : pct(comp.change_pct)}
                </dd></div>
            </dl>
            {comp.is_partial ? <p className="mt-4 text-[0.78rem] text-faint">The latest month is partial, so it&apos;s compared with the same number of days of the previous month.</p> : null}
          </Card>
        ) : (
          <EmptyState title="Not enough history to compare">
            A month-over-month comparison needs the previous month to be covered by your statements. Import an older
            statement, or widen the date range.
          </EmptyState>
        )}
      </section>

      {/* ---------- insight cards */}
      {cards.length ? (
        <section aria-labelledby="insights-title" className="space-y-4">
          <SectionHeader id="insights-title" title="Insights" subtitle="Every number is calculated from your transactions. Open any card to see the rows behind it." />
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {cards.map((i) => <InsightCard key={i.key} insight={i} onOpen={(x) => x.link && openTransactions(x.link)} />)}
          </div>
        </section>
      ) : null}

      {/* ---------- drivers */}
      {comp ? (
        <section aria-labelledby="drivers-title" className="space-y-4">
          <SectionHeader id="drivers-title" title="Drivers of the change" subtitle={`${comp.current.label} vs ${comp.previous.label}`} />
          <div className="grid grid-cols-1 gap-5 xl:grid-cols-[1.4fr_1fr]">
            <ChartContainer title="By category" subtitle="Spending in each period" height={320}
              table={{ columns: ["Category", comp.previous.label, comp.current.label, "Change"],
                rows: data.category_changes.map((c) => [c.category, inr(c.previous_paise), inr(c.current_paise), inr(c.change_paise, { sign: true })]) }}>
              <CompareChart data={data.category_changes} previousLabel={comp.previous.label} currentLabel={comp.current.label} />
            </ChartContainer>
            <Card className="p-4 sm:p-5">
              <SectionHeader title="By merchant" subtitle="Where the change came from" level={3} />
              {[{ title: "Spent more at", rows: more, tone: "neg" as const }, { title: "Spent less at", rows: less, tone: "pos" as const }].map((group) => (
                <div key={group.title} className="mt-4">
                  <p className="eyebrow mb-2 text-[0.6rem]">{group.title}</p>
                  {group.rows.length === 0 ? <p className="text-[0.8rem] text-faint">Nothing to show.</p> : (
                    <ul className="divide-y divide-line/60">
                      {group.rows.map((m) => (
                        <li key={m.merchant}>
                          <button type="button" onClick={() => openTransactions({ start: comp.previous.start, end: comp.current.end, merchants: [m.merchant] })}
                            className="group flex w-full items-center justify-between gap-3 py-2 text-left">
                            <span className="min-w-0">
                              <span className="block truncate text-[0.85rem] text-fg">{m.merchant}</span>
                              <span className="tabular text-[0.72rem] text-faint">{inr(m.previous_paise)} → {inr(m.current_paise)}</span>
                            </span>
                            <span className={`tabular flex items-center gap-1 text-[0.85rem] ${group.tone === "neg" ? "text-neg" : "text-pos"}`}>
                              {inr(m.change_paise, { sign: true })}
                              <ArrowRight className="h-3.5 w-3.5 text-faint transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </Card>
          </div>
        </section>
      ) : null}

      {/* ---------- patterns */}
      <section aria-labelledby="patterns-title" className="space-y-4">
        <SectionHeader id="patterns-title" title="Patterns" subtitle="Across the selected period" />
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-[1.4fr_1fr]">
          <ChartContainer title="Spending by weekday" subtitle="Total expenditure on each day of the week" height={260}
            table={{ columns: ["Day", "Spent", "Payments"], rows: data.weekday.map((w) => [w.weekday_name, inr(w.expenditure_paise), w.transaction_count]) }}>
            <WeekdayChart data={data.weekday} />
          </ChartContainer>
          <Card className="p-4 sm:p-5">
            <SectionHeader title="Largest payments" level={3} />
            <ul className="mt-3 divide-y divide-line/60">
              {data.largest.map((l) => (
                <li key={l.id} className="flex items-center justify-between gap-3 py-2.5">
                  <span className="min-w-0">
                    <span className="block truncate text-[0.85rem] text-fg">{l.merchant}</span>
                    <span className="text-[0.72rem] text-faint">{fmtDate(l.transaction_date)} · {l.category}</span>
                  </span>
                  <span className="tabular text-[0.88rem] text-fg">{inr(l.amount_paise)}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </section>

      {/* ---------- anomalies */}
      <AnomalySection anomalies={data.anomalies} info={data.anomaly_info} busyId={busyId} onReview={review} onOpen={openTransactions} />
    </div>
  );
}
