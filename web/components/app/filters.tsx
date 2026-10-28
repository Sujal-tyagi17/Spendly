"use client";

import { CalendarRange, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { EMPTY_FILTERS } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { useApp } from "@/lib/store";
import { Button } from "../ui/button";
import { MultiSelect } from "../ui/multi-select";

function usePopover() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", key); };
  }, [open]);
  return { open, setOpen, ref };
}

function shiftMonths(iso: string, months: number): string {
  const [y, m] = iso.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1 + months, 1));
  return d.toISOString().slice(0, 10);
}

export function DateRangeSelector() {
  const { meta, filters, setFilters } = useApp();
  const { open, setOpen, ref } = usePopover();
  const min = meta?.date_bounds.min ?? undefined;
  const max = meta?.date_bounds.max ?? undefined;
  const [start, setStart] = useState(filters.start ?? "");
  const [end, setEnd] = useState(filters.end ?? "");

  const openPanel = () => {
    setStart(filters.start ?? min ?? "");
    setEnd(filters.end ?? max ?? "");
    setOpen((o) => !o);
  };

  const label = filters.start || filters.end
    ? `${fmtDate(filters.start ?? min, { year: false })} – ${fmtDate(filters.end ?? max)}`
    : "All dates";

  const apply = (s: string | null, e: string | null) => {
    setFilters({ ...filters, start: s && s !== min ? s : null, end: e && e !== max ? e : null });
    setOpen(false);
  };
  const invalid = !!start && !!end && start > end;

  const presets = max ? [
    { label: "All dates", s: null, e: null },
    { label: "Latest month", s: max.slice(0, 8) + "01", e: max },
    { label: "Last 3 months", s: shiftMonths(max, -2), e: max },
  ] : [];

  return (
    <div ref={ref} className="relative">
      <button type="button" onClick={openPanel} aria-expanded={open} aria-haspopup="dialog" disabled={!max}
        className="inline-flex h-10 items-center gap-2 rounded-xl border border-line bg-ink-2 px-3 text-[0.82rem] text-fg transition-colors hover:border-line-2 disabled:opacity-50">
        <CalendarRange className="h-4 w-4 text-lime-2" aria-hidden="true" />
        <span className="tabular whitespace-nowrap">{label}</span>
      </button>
      {open ? (
        <div role="dialog" aria-label="Choose a date range"
          className="absolute right-0 z-50 mt-2 w-[min(20rem,calc(100vw-2rem))] rounded-2xl border border-line-2 bg-elevated p-4 shadow-[0_24px_48px_-20px_rgb(0_0_0/0.9)]">
          <div className="mb-3 flex flex-wrap gap-1.5">
            {presets.map((p) => (
              <button key={p.label} type="button" onClick={() => apply(p.s, p.e)}
                className="rounded-lg border border-line px-2.5 py-1.5 text-[0.75rem] text-muted transition-colors hover:border-line-2 hover:text-fg">
                {p.label}
              </button>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-2">
            <label className="text-[0.72rem] text-muted">From
              <input type="date" value={start} min={min} max={max} onChange={(e) => setStart(e.target.value)}
                className="mt-1 h-10 w-full rounded-xl border border-line bg-ink-2 px-2 text-[0.82rem] text-fg [color-scheme:dark]" />
            </label>
            <label className="text-[0.72rem] text-muted">To
              <input type="date" value={end} min={min} max={max} onChange={(e) => setEnd(e.target.value)}
                className="mt-1 h-10 w-full rounded-xl border border-line bg-ink-2 px-2 text-[0.82rem] text-fg [color-scheme:dark]" />
            </label>
          </div>
          {invalid ? <p role="alert" className="mt-2 text-[0.75rem] text-[#ff9b8f]">The start date is after the end date.</p> : null}
          <p className="mt-2 text-[0.72rem] text-faint">Your data covers {fmtDate(min)} – {fmtDate(max)}.</p>
          <div className="mt-3 flex justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
            <Button size="sm" variant="primary" disabled={invalid} onClick={() => apply(start || null, end || null)}>Apply</Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function FilterButton() {
  const { meta, filters, setFilters, activeFilterCount } = useApp();
  const { open, setOpen, ref } = usePopover();
  const count = filters.categories.length + filters.types.length + filters.merchants.length;
  return (
    <div ref={ref} className="relative">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-haspopup="dialog"
        className={`inline-flex h-10 items-center gap-2 rounded-xl border px-3 text-[0.82rem] transition-colors ${
          count ? "border-lime/40 bg-lime/[0.06] text-fg" : "border-line bg-ink-2 text-fg hover:border-line-2"}`}>
        <SlidersHorizontal className="h-4 w-4 text-lime-2" aria-hidden="true" />
        Filters
        {count ? <span className="tabular rounded-md bg-lime px-1.5 text-[0.7rem] font-semibold text-ink">{count}</span> : null}
      </button>
      {open ? (
        <div role="dialog" aria-label="Filters"
          className="absolute right-0 z-50 mt-2 w-[min(22rem,calc(100vw-2rem))] space-y-3 rounded-2xl border border-line-2 bg-elevated p-4 shadow-[0_24px_48px_-20px_rgb(0_0_0/0.9)]">
          <MultiSelect label="Category" placeholder="All categories" value={filters.categories}
            options={(meta?.categories ?? []).map((c) => ({ value: c, label: c }))}
            onChange={(categories) => setFilters({ ...filters, categories })} />
          <MultiSelect label="Transaction type" placeholder="All types" value={filters.types}
            options={(meta?.transaction_types ?? []).map((t) => ({ value: t.key, label: t.label }))}
            onChange={(types) => setFilters({ ...filters, types })} />
          <MultiSelect label="Merchant" placeholder="All merchants" searchable value={filters.merchants}
            options={(meta?.merchants ?? []).map((m) => ({ value: m, label: m }))}
            onChange={(merchants) => setFilters({ ...filters, merchants })} />
          <p className="text-[0.72rem] leading-relaxed text-faint">Filters apply to every page, like the date range.</p>
          {activeFilterCount ? (
            <Button size="sm" variant="ghost" onClick={() => setFilters(EMPTY_FILTERS)}>
              <X className="h-3.5 w-3.5" aria-hidden="true" /> Clear all filters
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/** Removable chips summarising the active filters (visible on every page). */
export function ActiveFilterChips() {
  const { filters, setFilters, meta } = useApp();
  const typeLabel = (k: string) => meta?.transaction_types.find((t) => t.key === k)?.label ?? k;
  const chips: { key: string; label: string; remove: () => void }[] = [];
  if (filters.start || filters.end) chips.push({
    key: "dates", label: `${fmtDate(filters.start ?? meta?.date_bounds.min, { year: false })} – ${fmtDate(filters.end ?? meta?.date_bounds.max)}`,
    remove: () => setFilters({ ...filters, start: null, end: null }),
  });
  filters.categories.forEach((c) => chips.push({ key: `c-${c}`, label: c, remove: () => setFilters({ ...filters, categories: filters.categories.filter((x) => x !== c) }) }));
  filters.types.forEach((t) => chips.push({ key: `t-${t}`, label: typeLabel(t), remove: () => setFilters({ ...filters, types: filters.types.filter((x) => x !== t) }) }));
  filters.merchants.forEach((m) => chips.push({ key: `m-${m}`, label: m, remove: () => setFilters({ ...filters, merchants: filters.merchants.filter((x) => x !== m) }) }));
  if (!chips.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5" aria-label="Active filters">
      {chips.map((c) => (
        <button key={c.key} type="button" onClick={c.remove} aria-label={`Remove filter ${c.label}`}
          className="inline-flex items-center gap-1 rounded-lg border border-lime/25 bg-lime/[0.06] px-2 py-1 text-[0.72rem] text-fg/90 transition-colors hover:border-lime/50">
          {c.label}
          <X className="h-3 w-3 text-muted" aria-hidden="true" />
        </button>
      ))}
      {chips.length > 1 ? (
        <button type="button" onClick={() => setFilters(EMPTY_FILTERS)} className="px-1.5 text-[0.72rem] text-muted underline-offset-2 hover:text-fg hover:underline">
          Clear all
        </button>
      ) : null}
    </div>
  );
}
