"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef } from "react";
import { Button } from "./button";

/** Modal confirmation. Escape / backdrop cancel; focus moves into the dialog and back. */
export function ConfirmDialog({ open, title, children, confirmLabel = "Confirm", tone = "primary", busy = false,
  confirmDisabled = false, onConfirm, onCancel }: {
  open: boolean; title: string; children?: React.ReactNode; confirmLabel?: string; tone?: "primary" | "danger";
  busy?: boolean; confirmDisabled?: boolean; onConfirm: () => void; onCancel: () => void;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const previous = useRef<Element | null>(null);

  useEffect(() => {
    if (!open) return;
    previous.current = document.activeElement;
    const t = window.setTimeout(() => {
      const first = panel.current?.querySelector<HTMLElement>("input, select, textarea, button");
      first?.focus();
    }, 30);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
      if (e.key === "Tab" && panel.current) {
        const items = panel.current.querySelectorAll<HTMLElement>("button, input, select, textarea, a[href]");
        if (!items.length) return;
        const first = items[0], last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.clearTimeout(t);
      window.removeEventListener("keydown", onKey);
      (previous.current as HTMLElement | null)?.focus?.();
    };
  }, [open, onCancel]);

  return (
    <AnimatePresence>
      {open ? (
        <motion.div className="fixed inset-0 z-[80] flex items-end justify-center p-4 sm:items-center"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
          <div className="absolute inset-0 bg-black/70 backdrop-blur-[2px]" onClick={onCancel} aria-hidden="true" />
          <motion.div ref={panel} role="dialog" aria-modal="true" aria-labelledby="confirm-title"
            initial={{ y: 16, opacity: 0, scale: 0.98 }} animate={{ y: 0, opacity: 1, scale: 1 }} exit={{ y: 8, opacity: 0 }}
            transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
            className="relative w-full max-w-md rounded-2xl border border-line-2 bg-elevated p-6 shadow-[0_40px_80px_-30px_rgb(0_0_0/0.9)]">
            <h2 id="confirm-title" className="text-lg font-semibold tracking-tight text-fg">{title}</h2>
            <div className="mt-2 text-[0.9rem] leading-relaxed text-muted">{children}</div>
            <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <Button onClick={onCancel}>Cancel</Button>
              <Button variant={tone === "danger" ? "danger" : "primary"} onClick={onConfirm} loading={busy} disabled={confirmDisabled}>
                {confirmLabel}
              </Button>
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
