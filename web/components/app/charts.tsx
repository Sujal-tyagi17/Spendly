"use client";

import { useReducedMotion } from "motion/react";
import { useState } from "react";
import {
  Area, Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { inr, inrCompact, monthLabel } from "@/lib/format";
import { SectionHeader } from "../ui/card";

const C = {
  lime: "#c6ff5e",
  lime2: "#a8e65c",
  grid: "#1e261e",
  axis: "#828a80",
  prev: "#56604f",
  income: "#8fb8de",
};

const axisProps = {
  tick: { fill: C.axis, fontSize: 11 },
  tickLine: false,
  axisLine: false,
} as const;

type TipPayload = { name?: string; value?: number | null; color?: string; dataKey?: string | number };

function ChartTooltip({ active, payload, label, labelFormat }: {
  active?: boolean; payload?: TipPayload[]; label?: string; labelFormat?: (l: string) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-line-2 bg-elevated/95 px-3 py-2.5 text-[0.78rem] shadow-[0_16px_32px_-12px_rgb(0_0_0/0.9)]">
      <p className="mb-1.5 font-medium text-fg">{labelFormat ? labelFormat(String(label)) : label}</p>
      {payload.map((p) => (
        <p key={String(p.dataKey)} className="flex items-center gap-2 text-muted">
          <span className="h-2 w-2 rounded-full" style={{ background: p.color }} aria-hidden="true" />
          {p.name}: <span className="tabular text-fg">{p.value === null || p.value === undefined ? "no statement" : inr(p.value * 100)}</span>
        </p>
      ))}
    </div>
  );
}

/** Card wrapper with an accessible "view as table" fallback for every chart. */
export function ChartContainer({ title, subtitle, table, children, height = 280, action }: {
  title: string; subtitle?: string; table: { columns: string[]; rows: (string | number)[][] };
  children: React.ReactNode; height?: number; action?: React.ReactNode;
}) {
  const [asTable, setAsTable] = useState(false);
  return (
    <section className="rounded-2xl border border-line bg-card p-4 sm:p-5">
      <SectionHeader title={title} subtitle={subtitle} action={
        <>
          {action}
          <button type="button" onClick={() => setAsTable((v) => !v)} aria-pressed={asTable}
            className="rounded-lg px-2 py-1 text-[0.72rem] text-faint transition-colors hover:bg-white/[0.04] hover:text-fg">
            {asTable ? "Show chart" : "View as table"}
          </button>
        </>
      } />
      <div className="mt-4" style={{ minHeight: height }}>
        {asTable ? (
          <div className="relative overflow-x-auto">
            <table className="w-full text-left text-[0.8rem]">
              <thead>
                <tr className="border-b border-line text-muted">
                  {table.columns.map((c, i) => <th key={c} scope="col" className={`py-2 pr-4 font-medium ${i ? "text-right" : ""}`}>{c}</th>)}
                </tr>
              </thead>
              <tbody>
                {table.rows.map((r, i) => (
                  <tr key={i} className="border-b border-line/50">
                    {r.map((cell, j) => <td key={j} className={`tabular py-2 pr-4 ${j ? "text-right text-fg/85" : "text-fg"}`}>{cell}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div style={{ height }} aria-hidden="true">{children}</div>
        )}
      </div>
    </section>
  );
}

export type MonthRow = { month_start: string; expenditure_paise: number; income_paise: number; is_covered?: number | boolean };

/** Rows from the API say whether a statement covers the month; older payloads without the flag count as covered. */
function covered(d: { is_covered?: number | boolean }): boolean {
  return d.is_covered === undefined || Boolean(d.is_covered);
}

export function TrendChart({ data, onSelectMonth }: { data: MonthRow[]; onSelectMonth?: (monthStart: string) => void }) {
  const reduced = useReducedMotion();
  // A month no statement covers is missing data, not ₹0: leave a gap instead of drawing a dip to zero.
  const rows = data.map((d) => ({ month: d.month_start, Expenditure: covered(d) ? d.expenditure_paise / 100 : null,
    Income: covered(d) ? d.income_paise / 100 : null }));
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
        style={onSelectMonth ? { cursor: "pointer" } : undefined}
        onClick={onSelectMonth ? (state) => { const l = (state as { activeLabel?: string | number } | null)?.activeLabel; if (l) onSelectMonth(String(l)); } : undefined}>
        <defs>
          <linearGradient id="spendFill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={C.lime2} stopOpacity={0.22} />
            <stop offset="100%" stopColor={C.lime2} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={C.grid} vertical={false} />
        <XAxis dataKey="month" tickFormatter={monthLabel} {...axisProps} dy={6} />
        <YAxis tickFormatter={(v) => inrCompact(v * 100)} width={56} {...axisProps} />
        <Tooltip content={<ChartTooltip labelFormat={monthLabel} />} cursor={{ stroke: "#2a342a" }} />
        <Legend verticalAlign="top" align="right" height={28} iconType="plainline"
          formatter={(v) => <span className="text-[0.75rem] text-muted">{v}</span>} />
        <Area type="linear" dataKey="Expenditure" stroke={C.lime2} strokeWidth={2} fill="url(#spendFill)"
          dot={{ r: 3, fill: C.lime2, strokeWidth: 0 }} activeDot={{ r: 5, stroke: "#0d100d", strokeWidth: 2 }}
          isAnimationActive={!reduced} animationDuration={900} />
        <Line type="linear" dataKey="Income" stroke={C.income} strokeWidth={1.5} strokeDasharray="5 4"
          dot={{ r: 2.5, fill: C.income, strokeWidth: 0 }} isAnimationActive={!reduced} animationDuration={900} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function WeekdayChart({ data }: { data: { weekday_name: string; expenditure_paise: number }[] }) {
  const reduced = useReducedMotion();
  const rows = data.map((d) => ({ day: d.weekday_name.slice(0, 3), full: d.weekday_name, Spent: d.expenditure_paise / 100 }));
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={rows} margin={{ top: 8, right: 4, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={C.grid} vertical={false} />
        <XAxis dataKey="day" {...axisProps} dy={6} />
        <YAxis tickFormatter={(v) => inrCompact(v * 100)} width={52} {...axisProps} />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgb(255 255 255 / 0.03)" }} />
        <Bar dataKey="Spent" fill={C.lime2} radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={!reduced} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function CompareChart({ data, previousLabel, currentLabel }: {
  data: { category: string; previous_paise: number; current_paise: number }[]; previousLabel: string; currentLabel: string;
}) {
  const reduced = useReducedMotion();
  const rows = [...data]
    .sort((a, b) => b.current_paise + b.previous_paise - (a.current_paise + a.previous_paise))
    .slice(0, 8)
    .map((d) => ({ category: d.category, [previousLabel]: d.previous_paise / 100, [currentLabel]: d.current_paise / 100 }));
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 12, bottom: 0, left: 4 }} barGap={2}>
        <CartesianGrid stroke={C.grid} horizontal={false} />
        <XAxis type="number" tickFormatter={(v) => inrCompact(v * 100)} {...axisProps} />
        <YAxis type="category" dataKey="category" width={112} {...axisProps} tick={{ fill: "#c9cfc6", fontSize: 11 }} />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgb(255 255 255 / 0.03)" }} />
        <Legend verticalAlign="top" align="right" height={28} iconType="square"
          formatter={(v) => <span className="text-[0.75rem] text-muted">{v}</span>} />
        <Bar dataKey={previousLabel} fill={C.prev} radius={[0, 3, 3, 0]} maxBarSize={10} isAnimationActive={!reduced} />
        <Bar dataKey={currentLabel} fill={C.lime2} radius={[0, 3, 3, 0]} maxBarSize={10} isAnimationActive={!reduced} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Simple ranked bars (category / merchant breakdowns) — readable on any screen. */
export function RankedBars({ items, onSelect }: {
  items: { label: string; value: number; note?: string; share?: number | null }[];
  onSelect?: (label: string) => void;
}) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <ul className="space-y-3">
      {items.map((item, i) => {
        const content = (
          <>
            <div className="mb-1.5 flex items-baseline justify-between gap-3 text-[0.82rem]">
              <span className="truncate text-fg/90">{item.label}</span>
              <span className="tabular shrink-0 text-fg">
                {inr(item.value)}
                {item.share !== undefined && item.share !== null ? <span className="ml-2 text-faint">{item.share.toFixed(0)}%</span> : null}
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.05]">
              <div className={`h-full rounded-full transition-[width] duration-700 ease-out-soft ${i === 0 ? "bg-lime" : "bg-lime-2/45"}`}
                style={{ width: `${(item.value / max) * 100}%` }} />
            </div>
            {item.note ? <p className="mt-1 text-[0.72rem] text-faint">{item.note}</p> : null}
          </>
        );
        return (
          <li key={item.label}>
            {onSelect ? (
              <button type="button" onClick={() => onSelect(item.label)}
                className="block w-full rounded-lg text-left transition-opacity hover:opacity-90" aria-label={`Show ${item.label} transactions`}>
                {content}
              </button>
            ) : content}
          </li>
        );
      })}
    </ul>
  );
}

/** Income vs expenditure per month (two series, one ₹ axis). */
export function CashFlowChart({ data }: { data: { month_start: string; income_paise: number; expenditure_paise: number; is_covered?: number | boolean }[] }) {
  const reduced = useReducedMotion();
  const rows = data.map((d) => ({ month: d.month_start, Income: covered(d) ? d.income_paise / 100 : null,
    Expenditure: covered(d) ? d.expenditure_paise / 100 : null }));
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barGap={3}>
        <CartesianGrid stroke={C.grid} vertical={false} />
        <XAxis dataKey="month" tickFormatter={monthLabel} {...axisProps} dy={6} />
        <YAxis tickFormatter={(v) => inrCompact(v * 100)} width={56} {...axisProps} />
        <Tooltip content={<ChartTooltip labelFormat={monthLabel} />} cursor={{ fill: "rgb(255 255 255 / 0.03)" }} />
        <Legend verticalAlign="top" align="right" height={28} iconType="square"
          formatter={(v) => <span className="text-[0.75rem] text-muted">{v}</span>} />
        <Bar dataKey="Income" fill={C.income} radius={[4, 4, 0, 0]} maxBarSize={22} isAnimationActive={!reduced} />
        <Bar dataKey="Expenditure" fill={C.lime2} radius={[4, 4, 0, 0]} maxBarSize={22} isAnimationActive={!reduced} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Running net cash flow (single series). */
export function CumulativeChart({ data }: { data: { month_start: string; cumulative_net_cash_flow_paise: number }[] }) {
  const reduced = useReducedMotion();
  const rows = data.map((d) => ({ month: d.month_start, "Running net cash flow": d.cumulative_net_cash_flow_paise / 100 }));
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="cumFill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={C.lime2} stopOpacity={0.18} />
            <stop offset="100%" stopColor={C.lime2} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={C.grid} vertical={false} />
        <XAxis dataKey="month" tickFormatter={monthLabel} {...axisProps} dy={6} />
        <YAxis tickFormatter={(v) => inrCompact(v * 100)} width={56} {...axisProps} />
        <Tooltip content={<ChartTooltip labelFormat={monthLabel} />} cursor={{ stroke: "#2a342a" }} />
        <Area type="linear" dataKey="Running net cash flow" stroke={C.lime2} strokeWidth={2} fill="url(#cumFill)"
          dot={{ r: 3, fill: C.lime2, strokeWidth: 0 }} isAnimationActive={!reduced} animationDuration={900} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/** Spending to recurring merchants vs everything else, per month (stacked: parts of one total). */
export function RecurringChart({ data }: { data: { month_start: string; recurring_paise: number; expenditure_paise: number }[] }) {
  const reduced = useReducedMotion();
  const rows = data.map((d) => ({
    month: d.month_start,
    Recurring: d.recurring_paise / 100,
    "Everything else": (d.expenditure_paise - d.recurring_paise) / 100,
  }));
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={C.grid} vertical={false} />
        <XAxis dataKey="month" tickFormatter={monthLabel} {...axisProps} dy={6} />
        <YAxis tickFormatter={(v) => inrCompact(v * 100)} width={56} {...axisProps} />
        <Tooltip content={<ChartTooltip labelFormat={monthLabel} />} cursor={{ fill: "rgb(255 255 255 / 0.03)" }} />
        <Legend verticalAlign="top" align="right" height={28} iconType="square"
          formatter={(v) => <span className="text-[0.75rem] text-muted">{v}</span>} />
        <Bar dataKey="Recurring" stackId="s" fill={C.lime2} maxBarSize={26} isAnimationActive={!reduced} />
        <Bar dataKey="Everything else" stackId="s" fill={C.prev} radius={[4, 4, 0, 0]} maxBarSize={26} isAnimationActive={!reduced} />
      </BarChart>
    </ResponsiveContainer>
  );
}
