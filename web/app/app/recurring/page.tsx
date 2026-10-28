"use client";

import { AlertTriangle, CalendarClock, Check, CheckCircle2, CircleDashed, RotateCcw, X } from "lucide-react";
import { useState } from "react";
import { NoDataState } from "@/components/app/no-data";
import { Pill } from "@/components/ui/badges";
import { Button } from "@/components/ui/button";
import { Card, SectionHeader } from "@/components/ui/card";
import { InfoTip } from "@/components/ui/info-tip";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import { ApiError, apiSend } from "@/lib/api";
import { fmtDate, inr } from "@/lib/format";
import { useFiltered } from "@/lib/hooks";
import { useApp } from "@/lib/store";
import type { Recurring, RecurringResponse } from "@/lib/types";

const STATUS = {
  confirmed: { label: "Confirmed by you", tone: "lime" as const, icon: CheckCircle2 },
  high_confidence: { label: "Detected · high confidence", tone: "pos" as const, icon: CalendarClock },
  possible: { label: "Possible pattern", tone: "warn" as const, icon: CircleDashed },
  rejected: { label: "Not recurring", tone: "neutral" as const, icon: X },
};

function CandidateCard({ c, busy, onDecide }: { c: Recurring; busy: boolean; onDecide: (merchant: string, d: "confirmed" | "rejected" | null) => void }) {
  const s = STATUS[c.status];
  const Icon = s.icon;
  const reliableNext = (c.status === "confirmed" || c.status === "high_confidence") && !c.possibly_stopped;
  return (
    <Card as="article" className={`flex h-full flex-col p-4 sm:p-5 hover:border-line-2 ${c.status === "rejected" ? "opacity-70" : ""}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-[1rem] font-semibold text-fg">{c.merchant}</h3>
          <p className="text-[0.75rem] text-faint">{c.kind} · {c.category}</p>
        </div>
        <Pill tone={s.tone}><Icon className="h-3 w-3" aria-hidden="true" />{s.label}</Pill>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 text-[0.8rem]">
        <div><p className="text-faint">Typical amount</p>
          <p className="tabular mt-0.5 text-fg">{inr(c.median_amount_paise)}
            {c.min_amount_paise !== c.max_amount_paise ? <span className="block text-[0.72rem] text-faint">{inr(c.min_amount_paise)}–{inr(c.max_amount_paise)}</span> : null}</p></div>
        <div><p className="text-faint">Frequency</p><p className="mt-0.5 text-fg">{c.schedule.charAt(0).toUpperCase() + c.schedule.slice(1)} · {c.occurrences} payments</p></div>
        <div><p className="text-faint">Est. per month</p><p className="tabular mt-0.5 text-fg">{inr(c.est_monthly_paise)}</p></div>
        <div><p className="text-faint">Est. per year</p><p className="tabular mt-0.5 text-fg">{inr(c.est_annual_paise)}</p></div>
        <div><p className="text-faint">Last payment</p><p className="mt-0.5 text-fg">{fmtDate(c.last_payment)}</p></div>
        <div><p className="text-faint">Next expected</p>
          <p className="mt-0.5 text-fg">{reliableNext ? `≈ ${fmtDate(c.next_expected)}` : <span className="text-faint">Not estimated</span>}</p></div>
      </div>

      {c.possibly_stopped ? (
        <p className="mt-3 flex items-start gap-2 rounded-lg border border-warn/25 bg-warn/[0.05] px-3 py-2 text-[0.76rem] text-fg/85">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warn" aria-hidden="true" />No recent payment. It may have been cancelled, so it&apos;s left out of the totals.
        </p>
      ) : null}

      <details className="group mt-3 text-[0.78rem]">
        <summary className="cursor-pointer list-none text-muted transition-colors hover:text-fg">
          <span className="underline decoration-line-2 underline-offset-2">Why Spendly thinks this repeats</span>
        </summary>
        <p className="mt-2 leading-relaxed text-fg/80">{c.rationale}.</p>
      </details>

      <div className="mt-auto flex flex-wrap gap-2 pt-4">
        {c.status !== "confirmed" ? <Button size="sm" variant={c.status === "possible" ? "primary" : "secondary"} disabled={busy} onClick={() => onDecide(c.merchant, "confirmed")}>
          <Check className="h-3.5 w-3.5" aria-hidden="true" />Confirm</Button> : null}
        {c.status !== "rejected" ? <Button size="sm" variant="ghost" disabled={busy} onClick={() => onDecide(c.merchant, "rejected")}>
          <X className="h-3.5 w-3.5" aria-hidden="true" />Not recurring</Button> : null}
        {c.status === "confirmed" || c.status === "rejected" ? <Button size="sm" variant="ghost" disabled={busy} onClick={() => onDecide(c.merchant, null)}>
          <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />Undo</Button> : null}
      </div>
    </Card>
  );
}

export default function RecurringPage() {
  const { meta, refresh, notify } = useApp();
  const { data, error, initialLoading, reload } = useFiltered<RecurringResponse>("/api/recurring");
  const [busy, setBusy] = useState<string | null>(null);

  if (meta && meta.counts.transactions === 0) return <NoDataState />;
  if (error && !data) return <ErrorState message={error.message} onRetry={reload} />;
  if (initialLoading || !data) return <div className="space-y-4" role="status" aria-label="Loading"><Skeleton className="h-36" /><div className="grid gap-4 md:grid-cols-2"><Skeleton className="h-64" /><Skeleton className="h-64" /></div></div>;

  const decide = async (merchant: string, decision: "confirmed" | "rejected" | null) => {
    setBusy(merchant);
    try {
      await apiSend("/api/recurring/decision", "POST", { merchant, decision });
      notify(decision === "confirmed" ? `${merchant} confirmed as recurring.` : decision === "rejected" ? `${merchant} marked as not recurring.` : `Decision for ${merchant} undone.`);
      refresh();
    } catch (e) {
      notify(e instanceof ApiError ? e.message : "Couldn't save your decision.", "error");
    } finally {
      setBusy(null);
    }
  };

  const by = (status: Recurring["status"]) => data.candidates.filter((c) => c.status === status);
  const active = data.candidates.filter((c) => (c.status === "confirmed" || c.status === "high_confidence") && !c.possibly_stopped);
  const tol = data.settings.tolerance_days;
  const groups = [
    { key: "confirmed", title: "Confirmed subscriptions", subtitle: "You confirmed these." },
    { key: "high_confidence", title: "Detected patterns", subtitle: "Regular timing and a stable amount, but not confirmed by you yet." },
    { key: "possible", title: "Possible patterns", subtitle: "Weaker evidence. Confirm or reject them." },
    { key: "rejected", title: "Not recurring", subtitle: "You rejected these." },
  ] as const;

  return (
    <div className="space-y-8">
      <Card className="relative overflow-hidden p-5 sm:p-7">
        <div aria-hidden="true" className="pointer-events-none absolute -top-24 -right-16 h-64 w-64 rounded-full bg-lime/[0.06] blur-3xl" />
        <div className="grid gap-6 md:grid-cols-[1.2fr_1fr_1fr]">
          <div>
            <p className="eyebrow flex items-center gap-1">Estimated recurring spend
              <InfoTip label="estimated recurring spend">
                Sum of confirmed and high-confidence payments that are still active. It&apos;s each one&apos;s typical (median) amount, converted to a monthly figure.
                It&apos;s an estimate, not a bill.
              </InfoTip></p>
            <p className="tabular mt-2 text-[2.2rem] leading-none font-semibold tracking-tight">{inr(data.monthly_total_paise)}<span className="text-base font-normal text-muted"> /month</span></p>
            <p className="tabular mt-2 text-[0.85rem] text-muted">≈ {inr(data.annual_total_paise)} a year</p>
          </div>
          <div className="md:border-l md:border-line md:pl-6"><p className="eyebrow">Active</p>
            <p className="tabular mt-2 text-2xl font-semibold">{active.length}</p><p className="mt-1 text-[0.8rem] text-muted">confirmed or high-confidence</p></div>
          <div className="md:border-l md:border-line md:pl-6"><p className="eyebrow">To review</p>
            <p className="tabular mt-2 text-2xl font-semibold text-warn">{by("possible").length}</p><p className="mt-1 text-[0.8rem] text-muted">possible patterns</p></div>
        </div>
        <p className="mt-6 border-t border-line pt-4 text-[0.78rem] leading-relaxed text-faint">
          A merchant becomes a candidate after at least {data.settings.min_occurrences} payments. <b className="font-medium text-muted">High confidence</b> means every
          gap fits a schedule (weekly ±{tol.weekly}d, monthly ±{tol.monthly}d, quarterly ±{tol.quarterly}d, yearly ±{tol.yearly}d) and amounts stay within{" "}
          {Math.round(data.settings.high_amount_tolerance * 100)}% of the median. Only your confirmation makes it a confirmed subscription.
        </p>
      </Card>

      {data.candidates.length === 0 ? (
        <EmptyState icon={CalendarClock} title="No recurring payments found">
          Detection needs at least {data.settings.min_occurrences} payments to the same merchant at regular intervals. Import more months of statements to find them.
        </EmptyState>
      ) : groups.map((g) => {
        const items = by(g.key);
        if (!items.length) return null;
        return (
          <section key={g.key} aria-labelledby={`rec-${g.key}`} className="space-y-4">
            <SectionHeader id={`rec-${g.key}`} title={`${g.title} (${items.length})`} subtitle={g.subtitle} />
            <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
              {items.map((c) => <CandidateCard key={c.merchant} c={c} busy={busy === c.merchant} onDecide={decide} />)}
            </div>
          </section>
        );
      })}
    </div>
  );
}
