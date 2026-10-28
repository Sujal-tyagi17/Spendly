"use client";

import { AnimatePresence, motion } from "motion/react";
import { AlertOctagon, CheckCircle2, Info, X } from "lucide-react";
import { useApp } from "@/lib/store";

export function Toaster() {
  const { toasts, dismiss } = useApp();
  return (
    <div aria-live="polite" aria-atomic="false" className="pointer-events-none fixed right-4 bottom-4 z-[90] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2">
      <AnimatePresence initial={false}>
        {toasts.map((t) => {
          const Icon = t.tone === "error" ? AlertOctagon : t.tone === "info" ? Info : CheckCircle2;
          return (
            <motion.div key={t.id} layout initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, x: 24 }} transition={{ duration: 0.2 }}
              role={t.tone === "error" ? "alert" : "status"}
              className="pointer-events-auto flex items-start gap-3 rounded-xl border border-line-2 bg-elevated p-3.5 text-[0.86rem] text-fg shadow-[0_20px_40px_-15px_rgb(0_0_0/0.85)]">
              <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${t.tone === "error" ? "text-[#ff9b8f]" : t.tone === "info" ? "text-info" : "text-lime"}`} aria-hidden="true" />
              <p className="flex-1 leading-snug">{t.message}</p>
              <button type="button" onClick={() => dismiss(t.id)} aria-label="Dismiss notification" className="rounded text-faint hover:text-fg">
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
