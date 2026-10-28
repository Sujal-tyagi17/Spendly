"use client";

import { AlertTriangle, ArrowDownRight, ArrowRight, ArrowUpRight, Lightbulb } from "lucide-react";
import { inr, pct } from "@/lib/format";
import type { Insight } from "@/lib/types";

const toneMeta = {
  up: { icon: ArrowUpRight, cls: "text-neg", label: "Increase" },
  down: { icon: ArrowDownRight, cls: "text-pos", label: "Decrease" },
  warning: { icon: AlertTriangle, cls: "text-warn", label: "Needs attention" },
  good: { icon: Lightbulb, cls: "text-pos", label: "Good" },
  neutral: { icon: Lightbulb, cls: "text-lime-2", label: "Pattern" },
} as const;

export function InsightCard({ insight, onOpen, compact = false }: {
  insight: Insight; onOpen?: (insight: Insight) => void; compact?: boolean;
}) {
  const meta = toneMeta[insight.tone] ?? toneMeta.neutral;
  const Icon = meta.icon;
  // Change insights carry a signed amount and % change; others carry a share of expenditure.
  const isChange = ["overall_change", "biggest_increase", "biggest_decrease"].includes(insight.key);
  return (
    <article className={`group flex h-full flex-col rounded-2xl border border-line bg-card transition-[border-color,transform] duration-200 hover:-translate-y-0.5 hover:border-line-2 ${compact ? "p-4" : "p-5"}`}>
      <div className="flex items-center justify-between gap-2">
        <p className="eyebrow flex items-center gap-1.5 text-[0.6rem]">
          <Icon className={`h-3.5 w-3.5 ${meta.cls}`} aria-hidden="true" />
          <span>{insight.title}</span>
          <span className="sr-only">({meta.label})</span>
        </p>
        {insight.period ? <span className="truncate text-[0.68rem] text-faint">{insight.period}</span> : null}
      </div>
      {insight.value_paise !== null ? (
        <p className="tabular mt-3 flex flex-wrap items-baseline gap-x-2 text-[1.5rem] leading-none font-semibold tracking-tight text-fg">
          {inr(insight.value_paise, { sign: isChange })}
          {insight.value_pct !== null ? (
            isChange
              ? <span className={`text-[0.85rem] font-medium ${meta.cls}`}>{pct(insight.value_pct, { sign: true })}</span>
              : <span className="text-[0.8rem] font-normal text-muted">{insight.value_pct.toFixed(0)}% of spending</span>
          ) : null}
        </p>
      ) : null}
      <p className={`mt-2.5 flex-1 leading-relaxed text-fg/80 ${compact ? "text-[0.82rem]" : "text-[0.88rem]"}`}>{insight.text}</p>
      <div className="mt-3 flex items-center justify-between gap-2">
        {insight.subject ? <span className="truncate text-[0.72rem] text-muted">{insight.subject}</span> : <span />}
        {insight.link && onOpen ? (
          <button type="button" onClick={() => onOpen(insight)}
            className="inline-flex shrink-0 items-center gap-1 rounded-lg px-1.5 py-1 text-[0.75rem] font-medium text-lime transition-colors hover:bg-lime/10">
            View transactions <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
          </button>
        ) : null}
      </div>
    </article>
  );
}
