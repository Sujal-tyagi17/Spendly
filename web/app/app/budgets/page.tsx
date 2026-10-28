"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import {
  AlertTriangle, ArrowRight, CalendarRange, CheckCircle2, ChevronLeft, ChevronRight, CircleDashed, Copy, Gauge,
  Info, Pencil, PiggyBank, Plus, Trash2, TrendingUp, X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { NoDataState } from "@/components/app/no-data";
import { ChartContainer } from "@/components/app/charts";
import { Pill } from "@/components/ui/badges";
import { Button } from "@/components/ui/button";
import { Card, SectionHeader } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { InfoTip } from "@/components/ui/info-tip";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import { ApiError, apiSend, useApi } from "@/lib/api";
import { fmtDate, inr, inrCompact, monthLabel } from "@/lib/format";
import { useOpenTransactions } from "@/lib/hooks";
import { useApp } from "@/lib/store";
import type { BudgetDrivers, BudgetInsight, BudgetMonths, BudgetReport, BudgetRow, BudgetStatus } from "@/lib/types";

// Status → label, colour and icon. Colour is never the only signal: every status has text and an icon.
const STATUS: Record<BudgetStatus, { label: string; tone: "neutral" | "lime" | "warn" | "pos" | "neg"; icon: typeof CheckCircle2; bar: string }> = {
  over: { label: "Over budget", tone: "neg", icon: AlertTriangle, bar: "bg-neg" },
  at_limit: { label: "At limit", tone: "warn", icon: Gauge, bar: "bg-warn" },
  near: { label: "Near limit", tone: "warn", icon: Gauge, bar: "bg-warn" },
  within: { label: "Within budget", tone: "pos", icon: CheckCircle2, bar: "bg-lime-2" },
  no_budget: { label: "No budget", tone: "neutral", icon: CircleDashed, bar: "bg-faint" },
  no_data: { label: "No data", tone: "neutral", icon: CircleDashed, bar: "bg-faint" },
};

const C = { grid: "#1e261e", axis: "#5f675d", budget: "#56604f", actual: "#a8e65c", over: "#ff7a6b", line: "#e8eee4" };
const axisProps = { tick: { fill: C.axis, fontSize: 11 }, tickLine: false, axisLine: false } as const;
const inputCls = "mt-1.5 h-10 w-full rounded-xl border border-line bg-ink-2 px-3 text-[0.9rem] text-fg placeholder:text-faint";

const ym = (iso: string) => iso.slice(0, 7);
function shift(month: string, delta: number) {
  const [y, m] = month.split("-").map(Number);
  const i = y * 12 + (m - 1) + delta;
  return `${Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, "0")}`;
}
const longMonth = (m: string) => new Date(`${ym(m)}-01T00:00:00`).toLocaleDateString("en-IN", { month: "long", year: "numeric" });

function StatusPill({ status }: { status: BudgetStatus }) {
  const s = STATUS[status];
  const Icon = s.icon;
  return <Pill tone={s.tone}><Icon className="h-3 w-3" aria-hidden="true" />{s.label}</Pill>;
}

/** Progress bar. Fills to 100% max; an overspend shows a marker and the % in text. */
function Progress({ pct, status, label }: { pct: number | null; status: BudgetStatus; label: string }) {
  const reduced = useReducedMotion();
  const width = pct === null ? (status === "over" ? 100 : 0) : Math.min(pct, 100);
  return (
    <div className="relative h-2 w-full overflow-hidden rounded-full bg-white/[0.06]" role="progressbar"
      aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct === null ? undefined : Math.min(Math.round(pct), 100)}
      aria-valuetext={pct === null ? STATUS[status].label : `${pct.toFixed(1)}% used`}>
      <motion.div className={`h-full rounded-full ${STATUS[status].bar}`}
        initial={reduced ? false : { width: 0 }} animate={{ width: `${width}%` }} transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }} />
    </div>
  );
}

// ---------------------------------------------------------------- dialogs

type EditTarget = { mode: "create"; category: string | null } | { mode: "edit"; id: number; category: string | null; amount_paise: number };

function BudgetDialog({ target, month, categories, taken, onClose, onSaved }: {
  target: EditTarget | null; month: string; categories: string[]; taken: Set<string>;
  onClose: () => void; onSaved: (msg: string) => void;
}) {
  const [category, setCategory] = useState<string>("");
  const [amount, setAmount] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const panel = useRef<HTMLDivElement>(null);
  const previous = useRef<Element | null>(null);

  useEffect(() => {
    if (!target) return;
    previous.current = document.activeElement;
    /* eslint-disable react-hooks/set-state-in-effect -- reset the form for the newly opened dialog */
    setCategory(target.category ?? "__overall__");
    setAmount(target.mode === "edit" ? String(target.amount_paise / 100) : "");
    setError(null);
    /* eslint-enable react-hooks/set-state-in-effect */
    const t = window.setTimeout(() => panel.current?.querySelector<HTMLElement>("#budget-amount")?.focus(), 40);
    const key = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", key);
    return () => {
      window.clearTimeout(t);
      window.removeEventListener("keydown", key);
      (previous.current as HTMLElement | null)?.focus?.();
    };
  }, [target, onClose]);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!target) return;
    if (!amount.trim()) { setError("Enter an amount in rupees."); return; }
    setBusy(true);
    setError(null);
    const cat = category === "__overall__" ? null : category;
    try {
      if (target.mode === "create") await apiSend("/api/budgets", "POST", { month, category: cat, amount: amount.trim() });
      else await apiSend(`/api/budgets/${target.id}`, "PATCH", { amount: amount.trim() });
      onSaved(`${cat ?? "Overall"} budget ${target.mode === "create" ? "set" : "updated"} for ${longMonth(month)}.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save the budget.");
    } finally {
      setBusy(false);
    }
  };

  const options = target?.mode === "create"
    ? [...(taken.has("__overall__") ? [] : ["__overall__"]), ...categories.filter((c) => !taken.has(c))]
    : [];

  return (
    <AnimatePresence>
      {target ? (
        <motion.div className="fixed inset-0 z-[80] flex items-end justify-center p-4 sm:items-center"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
          <div className="absolute inset-0 bg-black/70 backdrop-blur-[2px]" onClick={onClose} aria-hidden="true" />
          <motion.div ref={panel} role="dialog" aria-modal="true" aria-labelledby="budget-dialog-title"
            initial={{ y: 16, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 8, opacity: 0 }} transition={{ duration: 0.2 }}
            className="relative w-full max-w-md rounded-2xl border border-line-2 bg-elevated p-6 shadow-[0_40px_80px_-30px_rgb(0_0_0/0.9)]">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 id="budget-dialog-title" className="text-lg font-semibold tracking-tight">
                  {target.mode === "create" ? "Set a budget" : `Edit ${target.category ?? "overall"} budget`}
                </h2>
                <p className="mt-1 text-[0.82rem] text-muted">{longMonth(month)}</p>
              </div>
              <button type="button" onClick={onClose} aria-label="Close" className="rounded-lg p-1.5 text-faint hover:bg-white/[0.05] hover:text-fg">
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            <form onSubmit={save} className="mt-5 space-y-4" noValidate>
              {target.mode === "create" ? (
                <label className="block text-[0.82rem] text-muted">Applies to
                  <select value={category} onChange={(e) => setCategory(e.target.value)} className={inputCls}>
                    {options.map((o) => <option key={o} value={o}>{o === "__overall__" ? "Overall monthly budget" : o}</option>)}
                  </select>
                </label>
              ) : null}
              <label className="block text-[0.82rem] text-muted" htmlFor="budget-amount">Amount (₹)</label>
              <div className="relative -mt-2.5">
                <span className="pointer-events-none absolute top-1/2 left-3 mt-[3px] -translate-y-1/2 text-faint" aria-hidden="true">₹</span>
                <input id="budget-amount" inputMode="decimal" autoComplete="off" value={amount} placeholder="5000"
                  onChange={(e) => setAmount(e.target.value)} aria-invalid={!!error} aria-describedby={error ? "budget-error" : "budget-hint"}
                  className={`${inputCls} pl-7 tabular`} />
              </div>
              <p id="budget-hint" className="text-[0.74rem] text-faint">Rupees, up to 2 decimals. ₹0 is allowed and means “no spending planned”.</p>
              {error ? <p id="budget-error" role="alert" className="rounded-lg border border-err/30 bg-err/10 px-3 py-2 text-[0.8rem] text-[#ffb4ab]">{error}</p> : null}
              <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-end">
                <Button onClick={onClose}>Cancel</Button>
                <Button type="submit" variant="primary" loading={busy} disabled={target.mode === "create" && !options.length}>Save budget</Button>
              </div>
            </form>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

// ---------------------------------------------------------------- pieces

function MonthPicker({ month, months, onChange }: { month: string; months: BudgetMonths | null; onChange: (m: string) => void }) {
  const known = new Map((months?.months ?? []).map((m) => [m.month, m]));
  const info = known.get(month);
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex items-center rounded-xl border border-line bg-ink-2">
        <button type="button" onClick={() => onChange(shift(month, -1))} aria-label="Previous month"
          className="flex h-10 w-10 items-center justify-center rounded-l-xl text-muted hover:bg-white/[0.04] hover:text-fg">
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
        </button>
        <label className="sr-only" htmlFor="budget-month">Budget month</label>
        <input id="budget-month" type="month" value={month} onChange={(e) => e.target.value && onChange(e.target.value)}
          className="h-10 w-[11.5rem] border-x border-line bg-transparent px-3 text-[0.86rem] text-fg [color-scheme:dark]" />
        <button type="button" onClick={() => onChange(shift(month, 1))} aria-label="Next month"
          className="flex h-10 w-10 items-center justify-center rounded-r-xl text-muted hover:bg-white/[0.04] hover:text-fg">
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
      <span className="text-[0.74rem] text-faint">
        {info?.has_data ? "Statement data" : "No statement data"} · {info?.has_budgets ? "budgets set" : "no budgets yet"}
      </span>
    </div>
  );
}

function InsightList({ items, onOpen }: { items: BudgetInsight[]; onOpen: (i: BudgetInsight) => void }) {
  if (!items.length) return null;
  const icon = { up: TrendingUp, down: TrendingUp, warning: AlertTriangle, neutral: Info };
  return (
    <section aria-labelledby="budget-insights" className="space-y-4">
      <SectionHeader id="budget-insights" title="What happened this month"
        subtitle="Observations from your recorded transactions. The pace line is an estimate and says so." />
      <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {items.map((i) => {
          const Icon = icon[i.tone] ?? Info;
          return (
            <li key={i.key} className={`flex flex-col rounded-2xl border bg-card p-4 ${i.kind === "estimate" ? "border-dashed border-line-2" : "border-line"}`}>
              <div className="flex items-center justify-between gap-2">
                <p className="eyebrow flex items-center gap-1.5 text-[0.6rem]">
                  <Icon className={`h-3.5 w-3.5 ${i.tone === "up" ? "text-neg" : i.tone === "warning" ? "text-warn" : i.tone === "down" ? "text-pos rotate-180" : "text-lime-2"}`} aria-hidden="true" />
                  {i.title}
                </p>
                <span className={`rounded-md px-1.5 py-0.5 text-[0.62rem] font-medium uppercase tracking-wider ${i.kind === "estimate" ? "bg-info/10 text-info" : "bg-white/[0.04] text-faint"}`}>
                  {i.kind === "estimate" ? "Estimate" : "Observed"}
                </span>
              </div>
              <p className="mt-2 text-[0.86rem] leading-relaxed text-fg/90">{i.text}</p>
              {i.link ? (
                <button type="button" onClick={() => onOpen(i)} className="mt-3 inline-flex items-center gap-1 self-start text-[0.76rem] text-lime-2 hover:text-lime">
                  See transactions<ArrowRight className="h-3 w-3" aria-hidden="true" />
                </button>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Drivers({ month, category }: { month: string; category: string }) {
  const { mode, version } = useApp();
  const { data, error, loading } = useApi<BudgetDrivers>(`/api/budgets/drivers?month=${ym(month)}&category=${encodeURIComponent(category)}`, [mode, version]);
  if (loading && !data) return <Skeleton className="mt-3 h-24" />;
  if (error || !data) return <p className="mt-3 text-[0.78rem] text-faint">Couldn&apos;t load the breakdown.</p>;
  if (!data.merchants.length) return <p className="mt-3 text-[0.78rem] text-faint">No spending in this category this month.</p>;
  return (
    <div className="mt-3 grid grid-cols-1 gap-4 border-t border-line pt-3 text-[0.78rem] sm:grid-cols-2">
      <div>
        <p className="mb-1.5 text-faint">Where it went</p>
        <ul className="space-y-1">
          {data.merchants.slice(0, 5).map((m) => (
            <li key={m.merchant} className="flex justify-between gap-3"><span className="truncate text-fg/85">{m.merchant} <span className="text-faint">×{m.transaction_count}</span></span>
              <span className="tabular text-fg">{inr(m.expenditure_paise)}</span></li>
          ))}
        </ul>
      </div>
      <div>
        <p className="mb-1.5 text-faint">Change vs previous month</p>
        {data.change.length ? (
          <ul className="space-y-1">
            {data.change.slice(0, 5).map((m) => (
              <li key={m.merchant} className="flex justify-between gap-3"><span className="truncate text-fg/85">{m.merchant}</span>
                <span className={`tabular ${m.change_paise > 0 ? "text-neg" : "text-pos"}`}>{inr(m.change_paise, { sign: true })}</span></li>
            ))}
          </ul>
        ) : <p className="text-faint">Same as last month.</p>}
      </div>
    </div>
  );
}

function CategoryRow({ row, month, onEdit, onDelete, onCreate, onOpen }: {
  row: BudgetRow; month: string; onEdit: (r: BudgetRow) => void; onDelete: (r: BudgetRow) => void;
  onCreate: (category: string) => void; onOpen: (category: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const budgeted = row.budget_paise !== null;
  return (
    <li className="rounded-2xl border border-line bg-card p-4 transition-colors hover:border-line-2">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="min-w-0">
          <h3 className="truncate text-[0.95rem] font-semibold text-fg">{row.category}</h3>
          <p className="text-[0.74rem] text-faint">{row.transaction_count} transaction{row.transaction_count === 1 ? "" : "s"}</p>
        </div>
        <StatusPill status={row.status} />
      </div>

      {row.status === "no_data" ? (
        <p className="tabular mt-3 text-[1.05rem] font-semibold">{inr(row.budget_paise)}
          <span className="text-[0.8rem] font-normal text-muted"> budgeted · spending unknown until a statement covers this month</span></p>
      ) : budgeted ? (
        <>
          <div className="mt-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <p className="tabular text-[1.05rem] font-semibold">{inr(row.actual_paise)}
              <span className="text-[0.8rem] font-normal text-muted"> of {inr(row.budget_paise)}</span></p>
            <p className="tabular text-[0.8rem] text-muted">
              {row.utilisation_pct !== null ? `${row.utilisation_pct.toFixed(1)}% used` : "₹0 budget"}
            </p>
          </div>
          <div className="mt-2"><Progress pct={row.utilisation_pct} status={row.status} label={`${row.category} budget used`} /></div>
          <p className={`tabular mt-2 text-[0.8rem] ${row.remaining_paise! < 0 ? "text-neg" : "text-fg/80"}`}>
            {row.remaining_paise! < 0
              ? <>{inr(-row.remaining_paise!)} over{row.variance_pct !== null ? ` (+${row.variance_pct.toFixed(1)}%)` : ""}</>
              : row.remaining_paise === 0 ? "Nothing left" : <>{inr(row.remaining_paise)} left</>}
          </p>
          {row.pace?.pace ? (
            <p className="mt-1.5 text-[0.74rem] text-info">Estimate: at this pace ≈ {inr(row.pace.projected_paise)} by month end.</p>
          ) : null}
        </>
      ) : (
        <p className="tabular mt-3 text-[1.05rem] font-semibold">{inr(row.actual_paise)} <span className="text-[0.8rem] font-normal text-muted">spent, no budget</span></p>
      )}

      <div className="mt-3 flex flex-wrap gap-1.5">
        {budgeted ? (
          <>
            <Button size="sm" variant="ghost" onClick={() => onEdit(row)} aria-label={`Edit ${row.category} budget`}><Pencil className="h-3.5 w-3.5" aria-hidden="true" />Edit</Button>
            <Button size="sm" variant="ghost" onClick={() => onDelete(row)} aria-label={`Delete ${row.category} budget`}><Trash2 className="h-3.5 w-3.5" aria-hidden="true" />Delete</Button>
          </>
        ) : (
          <Button size="sm" variant="secondary" onClick={() => onCreate(row.category)}><Plus className="h-3.5 w-3.5" aria-hidden="true" />Set budget</Button>
        )}
        {row.actual_paise > 0 ? (
          <>
            <Button size="sm" variant="ghost" aria-expanded={open} onClick={() => setOpen((v) => !v)}>{open ? "Hide breakdown" : "Why?"}</Button>
            <Button size="sm" variant="ghost" onClick={() => onOpen(row.category)}>Transactions<ArrowRight className="h-3 w-3" aria-hidden="true" /></Button>
          </>
        ) : null}
      </div>
      {open ? <Drivers month={month} category={row.category} /> : null}
    </li>
  );
}

function BudgetChart({ rows }: { rows: BudgetRow[] }) {
  const reduced = useReducedMotion();
  const data = rows.filter((r) => r.budget_paise !== null).map((r) => ({
    category: r.category, Budget: r.budget_paise! / 100, Actual: r.actual_paise / 100, over: r.status === "over",
  }));
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 12, bottom: 0, left: 4 }} barGap={2}>
        <CartesianGrid stroke={C.grid} horizontal={false} />
        <XAxis type="number" tickFormatter={(v) => inrCompact(v * 100)} {...axisProps} />
        <YAxis type="category" dataKey="category" width={112} {...axisProps} tick={{ fill: "#c9cfc6", fontSize: 11 }} />
        <Tooltip cursor={{ fill: "rgb(255 255 255 / 0.03)" }} contentStyle={{ background: "#151b14", border: "1px solid #2a342a", borderRadius: 12, fontSize: 12 }}
          labelStyle={{ color: "#f5f7f2" }} formatter={(v) => inr(Number(v) * 100)} />
        <Legend verticalAlign="top" align="right" height={28} iconType="square" formatter={(v) => <span className="text-[0.75rem] text-muted">{v}</span>} />
        <Bar dataKey="Budget" fill={C.budget} radius={[0, 3, 3, 0]} maxBarSize={10} isAnimationActive={!reduced} />
        <Bar dataKey="Actual" fill={C.actual} radius={[0, 3, 3, 0]} maxBarSize={10} isAnimationActive={!reduced}>
          {data.map((d) => <Cell key={d.category} fill={d.over ? C.over : C.actual} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function HistoryChart({ history }: { history: BudgetReport["history"] }) {
  const reduced = useReducedMotion();
  const data = history.map((h) => ({ month: h.month, Spent: h.actual_paise / 100, Budget: h.budget_paise === null ? null : h.budget_paise / 100 }));
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={C.grid} vertical={false} />
        <XAxis dataKey="month" tickFormatter={monthLabel} {...axisProps} dy={6} />
        <YAxis tickFormatter={(v) => inrCompact(v * 100)} width={56} {...axisProps} />
        <Tooltip cursor={{ fill: "rgb(255 255 255 / 0.03)" }} contentStyle={{ background: "#151b14", border: "1px solid #2a342a", borderRadius: 12, fontSize: 12 }}
          labelStyle={{ color: "#f5f7f2" }} labelFormatter={(l) => monthLabel(String(l))} formatter={(v) => (v === null ? "No budget" : inr(Number(v) * 100))} />
        <Legend verticalAlign="top" align="right" height={28} formatter={(v) => <span className="text-[0.75rem] text-muted">{v}</span>} />
        <Bar dataKey="Spent" fill={C.actual} radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={!reduced} />
        <Line dataKey="Budget" stroke={C.line} strokeDasharray="5 4" strokeWidth={1.5} dot={{ r: 3 }} connectNulls={false} isAnimationActive={!reduced} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

// ------------------------------------------------------------------ page

export default function BudgetsPage() {
  const { ready, mode, version, meta, refresh, notify } = useApp();
  const openTransactions = useOpenTransactions();
  const months = useApi<BudgetMonths>(ready ? "/api/budgets/months" : null, [mode, version]);
  const [month, setMonth] = useState<string | null>(null);
  const [lastMode, setLastMode] = useState(mode);
  if (lastMode !== mode) { setLastMode(mode); setMonth(null); }
  const current = month ?? months.data?.default ?? null;
  const report = useApi<BudgetReport>(current ? `/api/budgets?month=${current}` : null, [mode, version]);

  const [edit, setEdit] = useState<EditTarget | null>(null);
  const [toDelete, setToDelete] = useState<{ id: number; label: string } | null>(null);
  const [copyOpen, setCopyOpen] = useState(false);
  const [overwrite, setOverwrite] = useState(false);
  const [busy, setBusy] = useState(false);

  const closeEdit = useCallback(() => setEdit(null), []);
  const data = report.data;
  const taken = useMemo(() => {
    const s = new Set<string>();
    data?.rows.forEach((r) => r.budget_id !== null && s.add(r.category));
    if (data?.overall.overall_budget_id) s.add("__overall__");
    return s;
  }, [data]);

  if (meta && meta.counts.transactions === 0 && !months.data?.months.some((m) => m.has_budgets)) return <NoDataState />;
  const err = months.error ?? report.error;
  if (err && !data) return <ErrorState message={err.message} onRetry={() => { months.reload(); report.reload(); }} />;
  if (!current || !data) {
    return <div className="space-y-4" role="status" aria-label="Loading"><Skeleton className="h-40" /><div className="grid grid-cols-1 gap-4 md:grid-cols-2"><Skeleton className="h-56" /><Skeleton className="h-56" /></div></div>;
  }

  const o = data.overall;
  const cov = data.coverage;
  const budgetedRows = data.rows.filter((r) => r.budget_paise !== null);
  const unbudgetedRows = data.rows.filter((r) => r.budget_paise === null);
  const hasAny = budgetedRows.length > 0 || o.overall_budget_id !== null;
  const prevLabel = longMonth(data.previous_month);

  const saved = (msg: string) => { setEdit(null); notify(msg); refresh(); };
  const doDelete = async () => {
    if (!toDelete) return;
    setBusy(true);
    try {
      await apiSend(`/api/budgets/${toDelete.id}`, "DELETE");
      notify(`${toDelete.label} budget deleted.`);
      setToDelete(null);
      refresh();
    } catch (e) {
      notify(e instanceof ApiError ? e.message : "Couldn't delete the budget.", "error");
    } finally { setBusy(false); }
  };
  const doCopy = async () => {
    setBusy(true);
    try {
      const r = await apiSend<{ created: number; updated: number; skipped: number }>("/api/budgets/copy", "POST",
        { from_month: ym(data.previous_month), to_month: current, overwrite });
      notify(`Copied from ${prevLabel}: ${r.created} added${r.updated ? `, ${r.updated} replaced` : ""}${r.skipped ? `, ${r.skipped} kept as they were` : ""}.`);
      setCopyOpen(false);
      refresh();
    } catch (e) {
      notify(e instanceof ApiError ? e.message : "Couldn't copy budgets.", "error");
    } finally { setBusy(false); }
  };
  const openCategory = (category: string) => openTransactions({
    start: `${current}-01`, end: cov.covered_to ?? `${current}-28`, categories: [category], types: ["expense"],
  });

  const actions = (
    <div className="flex flex-wrap gap-2">
      <Button size="sm" variant="primary" onClick={() => setEdit({ mode: "create", category: o.overall_budget_id ? data.categories.find((c) => !taken.has(c)) ?? null : null })}
        disabled={taken.size >= data.categories.length + 1}>
        <Plus className="h-3.5 w-3.5" aria-hidden="true" />Add budget</Button>
      {data.previous_has_budgets ? (
        <Button size="sm" onClick={() => { setOverwrite(false); setCopyOpen(true); }}><Copy className="h-3.5 w-3.5" aria-hidden="true" />Copy from {prevLabel.split(" ")[0]}</Button>
      ) : null}
    </div>
  );

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <MonthPicker month={current} months={months.data} onChange={setMonth} />
        {actions}
      </div>

      {mode === "demo" ? (
        <p className="flex items-start gap-2 text-[0.78rem] text-faint"><Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          Demo budgets for Jul–Sep 2026 are synthetic. Edits here stay in the demo and are undone by resetting the demo.</p>
      ) : null}

      {!cov.is_covered ? (
        <div role="note" className="flex items-start gap-3 rounded-2xl border border-warn/25 bg-warn/[0.05] p-4 text-[0.84rem] text-fg/85">
          <CalendarRange className="mt-0.5 h-4 w-4 shrink-0 text-warn" aria-hidden="true" />
          <p>None of your statements cover {longMonth(current)}. You can still plan budgets here; spending appears once you import a statement for this month. No spending is shown as ₹0 because it is <b className="font-medium">unknown</b>, not zero.</p>
        </div>
      ) : !cov.is_full ? (
        <div role="note" className="flex items-start gap-3 rounded-2xl border border-info/25 bg-info/[0.05] p-4 text-[0.84rem] text-fg/85">
          <CalendarRange className="mt-0.5 h-4 w-4 shrink-0 text-info" aria-hidden="true" />
          <p>Partial month: statements cover {fmtDate(cov.covered_from)} – {fmtDate(cov.covered_to)} ({cov.days_covered} of {cov.days_in_month} days). Figures are spending <b className="font-medium">so far</b>, not the full month.</p>
        </div>
      ) : null}

      {/* ------------- overall summary */}
      <Card className="relative overflow-hidden p-5 sm:p-7">
        <div aria-hidden="true" className="pointer-events-none absolute -top-24 -right-16 h-64 w-64 rounded-full bg-lime/[0.06] blur-3xl" />
        <div className="grid grid-cols-1 gap-6 md:grid-cols-[1.3fr_1fr_1fr]">
          <div>
            <p className="eyebrow flex items-center gap-1">Overall budget · {longMonth(current)}
              <InfoTip label="overall budget">
                Your total plan for the month. Spending is expenditure only: transfers, card bill payments and income never count.
                Refunds are shown separately and are not subtracted from categories.
              </InfoTip></p>
            {o.overall_budget_paise !== null ? (
              <>
                {cov.is_covered ? (
                  <>
                    <p className="tabular mt-2 text-[2.1rem] leading-none font-semibold tracking-tight">{inr(o.expenditure_paise)}
                      <span className="text-base font-normal text-muted"> of {inr(o.overall_budget_paise)}</span></p>
                    <div className="mt-4 max-w-md"><Progress pct={o.utilisation_pct} status={o.status} label="Overall budget used" /></div>
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <StatusPill status={o.status} />
                      <span className={`tabular text-[0.84rem] ${o.remaining_paise! < 0 ? "text-neg" : "text-fg/85"}`}>
                        {o.remaining_paise! < 0 ? `${inr(-o.remaining_paise!)} over` : `${inr(o.remaining_paise)} left`}
                        {o.utilisation_pct !== null ? ` · ${o.utilisation_pct.toFixed(1)}% used` : ""}
                      </span>
                    </div>
                  </>
                ) : (
                  <>
                    <p className="tabular mt-2 text-[2.1rem] leading-none font-semibold tracking-tight">{inr(o.overall_budget_paise)}
                      <span className="text-base font-normal text-muted"> budgeted</span></p>
                    <div className="mt-3"><StatusPill status={o.status} /></div>
                  </>
                )}
                <div className="mt-3 flex gap-1.5">
                  <Button size="sm" variant="ghost" onClick={() => setEdit({ mode: "edit", id: o.overall_budget_id!, category: null, amount_paise: o.overall_budget_paise! })}>
                    <Pencil className="h-3.5 w-3.5" aria-hidden="true" />Edit</Button>
                  <Button size="sm" variant="ghost" onClick={() => setToDelete({ id: o.overall_budget_id!, label: "Overall" })}>
                    <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />Delete</Button>
                </div>
              </>
            ) : (
              <>
                {cov.is_covered
                  ? <p className="tabular mt-2 text-[2.1rem] leading-none font-semibold tracking-tight">{inr(o.expenditure_paise)}<span className="text-base font-normal text-muted"> spent</span></p>
                  : <p className="mt-2 text-[1.6rem] leading-none font-semibold tracking-tight text-muted">Spending unknown</p>}
                <p className="mt-3 text-[0.84rem] text-muted">No overall budget for this month.</p>
                <Button size="sm" className="mt-3" onClick={() => setEdit({ mode: "create", category: null })}><Plus className="h-3.5 w-3.5" aria-hidden="true" />Set overall budget</Button>
              </>
            )}
          </div>
          <div className="md:border-l md:border-line md:pl-6">
            <p className="eyebrow">Category budgets</p>
            <p className="tabular mt-2 text-2xl font-semibold">{inr(o.category_budgets_paise)}</p>
            <p className="mt-1 text-[0.8rem] text-muted">across {o.budgeted_category_count} categor{o.budgeted_category_count === 1 ? "y" : "ies"}</p>
            {o.overall_budget_paise !== null && o.category_budgets_paise > o.overall_budget_paise ? (
              <p className="mt-2 text-[0.74rem] text-warn">Category budgets add up to more than the overall budget.</p>
            ) : null}
          </div>
          <div className="md:border-l md:border-line md:pl-6">
            <p className="eyebrow">Outside category budgets</p>
            <p className="tabular mt-2 text-2xl font-semibold">{cov.is_covered ? inr(o.unbudgeted_paise) : "—"}</p>
            <p className="mt-1 text-[0.8rem] text-muted">spent in categories with no budget</p>
            {o.refunds_paise > 0 ? <p className="tabular mt-2 text-[0.74rem] text-faint">Refunds received: {inr(o.refunds_paise)} (net spend {inr(o.net_expenditure_paise)})</p> : null}
          </div>
        </div>
        {o.pace?.pace ? (
          <p className="mt-6 flex items-start gap-2 border-t border-dashed border-line-2 pt-4 text-[0.8rem] text-info">
            <Gauge className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            Estimate, not a result: after {o.pace.days_elapsed} days, a linear pace points to about {inr(o.pace.projected_paise)} by month end
            ({o.pace.days_remaining} days not yet in your statements).
          </p>
        ) : null}
      </Card>

      {!hasAny ? (
        <EmptyState icon={PiggyBank} title={`No budgets for ${longMonth(current)}`} action={actions}>
          Set an overall monthly budget or one per category. Spendly then compares it with what your statements show you actually spent.
          {data.previous_has_budgets ? ` You can also copy the budgets you set for ${prevLabel}.` : ""}
        </EmptyState>
      ) : (
        <>
          <InsightList items={data.insights} onOpen={(i) => i.link && openTransactions(i.link)} />

          {budgetedRows.length && cov.is_covered ? (
            <ChartContainer title="Budget vs actual" subtitle="Per category. Bars in red went over budget."
              height={Math.max(180, budgetedRows.length * 34 + 40)}
              table={{ columns: ["Category", "Budget", "Actual", "Remaining", "Used", "Status"],
                rows: budgetedRows.map((r) => [r.category, inr(r.budget_paise), inr(r.actual_paise), inr(r.remaining_paise),
                  r.utilisation_pct === null ? "—" : `${r.utilisation_pct.toFixed(1)}%`, STATUS[r.status].label]) }}>
              <BudgetChart rows={budgetedRows} />
            </ChartContainer>
          ) : null}

          {budgetedRows.length ? (
            <section aria-labelledby="budget-cats" className="space-y-4">
              <SectionHeader id="budget-cats" title={`Category budgets (${budgetedRows.length})`}
                subtitle={`Sorted by how far over or under budget. “Near limit” starts at ${data.settings.near_threshold_pct}% used.`} />
              <ul className="grid grid-cols-1 gap-3 md:grid-cols-2 2xl:grid-cols-3">
                {budgetedRows.map((r) => (
                  <CategoryRow key={r.category} row={r} month={current}
                    onEdit={(row) => setEdit({ mode: "edit", id: row.budget_id!, category: row.category, amount_paise: row.budget_paise! })}
                    onDelete={(row) => setToDelete({ id: row.budget_id!, label: row.category })}
                    onCreate={(c) => setEdit({ mode: "create", category: c })} onOpen={openCategory} />
                ))}
              </ul>
            </section>
          ) : null}
        </>
      )}

      {unbudgetedRows.length ? (
        <section aria-labelledby="budget-unbudgeted" className="space-y-4">
          <SectionHeader id="budget-unbudgeted" title={`Spending without a budget (${unbudgetedRows.length})`} subtitle="Recorded spending in categories you haven't budgeted for this month." />
          <ul className="grid grid-cols-1 gap-3 md:grid-cols-2 2xl:grid-cols-3">
            {unbudgetedRows.map((r) => (
              <CategoryRow key={r.category} row={r} month={current} onEdit={() => {}} onDelete={() => {}}
                onCreate={(c) => setEdit({ mode: "create", category: c })} onOpen={openCategory} />
            ))}
          </ul>
        </section>
      ) : null}

      {data.history.length > 1 ? (
        <ChartContainer title="Month by month" subtitle="Spending vs the overall budget (or the sum of category budgets when no overall budget is set)."
          table={{ columns: ["Month", "Spent", "Budget", "Basis"], rows: data.history.map((h) => [monthLabel(h.month), inr(h.actual_paise),
            h.budget_paise === null ? "—" : inr(h.budget_paise), h.budget_basis ?? "no budget"]) }}>
          <HistoryChart history={data.history} />
        </ChartContainer>
      ) : null}

      <p className="text-[0.74rem] leading-relaxed text-faint">
        Utilisation = spent ÷ budget × 100. Variance = spent − budget (positive means over). A ₹0 budget has no utilisation %;
        any spending against it counts as over. Going over a budget is a fact about the plan, not a judgement about the spending.
      </p>

      <BudgetDialog target={edit} month={current} categories={data.categories} taken={taken} onClose={closeEdit} onSaved={saved} />

      <ConfirmDialog open={!!toDelete} title={`Delete the ${toDelete?.label ?? ""} budget?`} tone="danger" confirmLabel="Delete budget"
        busy={busy} onConfirm={doDelete} onCancel={() => setToDelete(null)}>
        This removes the {toDelete?.label.toLowerCase() === "overall" ? "overall" : toDelete?.label} budget for {longMonth(current)}. Your transactions are not affected.
      </ConfirmDialog>

      <ConfirmDialog open={copyOpen} title={`Copy budgets from ${prevLabel}?`} confirmLabel="Copy budgets" busy={busy}
        onConfirm={doCopy} onCancel={() => setCopyOpen(false)}>
        Every budget from {prevLabel} is added to {longMonth(current)}.
        <label className="mt-3 flex items-center gap-2 text-[0.84rem] text-fg/85">
          <input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} className="h-4 w-4 accent-[#c6ff5e]" />
          Replace budgets already set for {longMonth(current).split(" ")[0]}
        </label>
      </ConfirmDialog>
    </div>
  );
}
