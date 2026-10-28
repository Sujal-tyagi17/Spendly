"use client";

import { Info } from "lucide-react";
import { useId, useState } from "react";

/** Explains a metric. Opens on hover, keyboard focus or tap — never hover-only. */
export function InfoTip({ label, children, align = "left" }: { label: string; children: React.ReactNode; align?: "left" | "right" }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <span className="relative inline-flex" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button
        type="button"
        aria-label={`About ${label}`}
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
        className="inline-flex h-5 w-5 items-center justify-center rounded-full text-faint transition-colors hover:text-fg"
      >
        <Info className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
      {open ? (
        <span role="tooltip" id={id}
          className={`absolute top-6 z-40 w-64 rounded-xl border border-line-2 bg-card-2 p-3 text-[0.78rem] leading-relaxed font-normal normal-case tracking-normal text-fg/90 shadow-[0_20px_40px_-15px_rgb(0_0_0/0.8)] ${align === "right" ? "right-0" : "left-0"}`}>
          {children}
        </span>
      ) : null}
    </span>
  );
}
