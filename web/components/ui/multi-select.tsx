"use client";

import { Check, ChevronDown, Search } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

export function MultiSelect({ label, options, value, onChange, searchable = false, placeholder }: {
  label: string;
  options: { value: string; label: string }[];
  value: string[];
  onChange: (v: string[]) => void;
  searchable?: boolean;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const root = useRef<HTMLDivElement>(null);
  const id = useId();

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", key); };
  }, [open]);

  const shown = options.filter((o) => o.label.toLowerCase().includes(query.toLowerCase())).slice(0, 200);
  const toggle = (v: string) => onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v]);
  const summary = value.length === 0 ? (placeholder ?? `All`) : value.length === 1
    ? options.find((o) => o.value === value[0])?.label ?? value[0] : `${value.length} selected`;

  return (
    <div ref={root} className="relative">
      <span id={`${id}-label`} className="mb-1.5 block text-[0.72rem] font-medium text-muted">{label}</span>
      <button type="button" aria-haspopup="listbox" aria-expanded={open} aria-labelledby={`${id}-label ${id}-btn`} id={`${id}-btn`}
        onClick={() => setOpen((o) => !o)}
        className="flex h-10 w-full items-center justify-between gap-2 rounded-xl border border-line bg-ink-2 px-3 text-left text-[0.85rem] text-fg transition-colors hover:border-line-2">
        <span className={`truncate ${value.length ? "text-fg" : "text-muted"}`}>{summary}</span>
        <ChevronDown className={`h-4 w-4 shrink-0 text-faint transition-transform ${open ? "rotate-180" : ""}`} aria-hidden="true" />
      </button>
      {open ? (
        <div className="absolute z-50 mt-1.5 w-full min-w-[14rem] rounded-xl border border-line-2 bg-elevated p-1.5 shadow-[0_24px_48px_-20px_rgb(0_0_0/0.9)]">
          {searchable ? (
            <label className="mb-1 flex items-center gap-2 rounded-lg border border-line bg-ink-2 px-2.5">
              <Search className="h-3.5 w-3.5 text-faint" aria-hidden="true" />
              <input autoFocus value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search…"
                aria-label={`Search ${label}`} className="h-8 w-full bg-transparent text-[0.82rem] text-fg outline-none placeholder:text-faint" />
            </label>
          ) : null}
          <ul role="listbox" aria-multiselectable="true" aria-label={label} className="max-h-64 overflow-y-auto">
            {shown.length === 0 ? <li className="px-2.5 py-2 text-[0.8rem] text-faint">No matches</li> : null}
            {shown.map((o) => {
              const selected = value.includes(o.value);
              return (
                <li key={o.value} role="option" aria-selected={selected}>
                  <button type="button" onClick={() => toggle(o.value)}
                    className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[0.84rem] text-fg/90 hover:bg-white/[0.05]">
                    <span className={`inline-flex h-4 w-4 shrink-0 items-center justify-center rounded border ${selected ? "border-lime bg-lime text-ink" : "border-line-2"}`}>
                      {selected ? <Check className="h-3 w-3" aria-hidden="true" /> : null}
                    </span>
                    <span className="truncate">{o.label}</span>
                  </button>
                </li>
              );
            })}
          </ul>
          {value.length ? (
            <button type="button" onClick={() => onChange([])} className="mt-1 w-full rounded-lg px-2.5 py-1.5 text-left text-[0.78rem] text-muted hover:text-fg">
              Clear selection
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
