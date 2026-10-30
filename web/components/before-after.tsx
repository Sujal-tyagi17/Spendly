"use client";

import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { formatINR, rawToStructured } from "@/lib/demo-data";
import { Reveal } from "./reveal";
import { SectionHeading, SyntheticBadge } from "./section-heading";

const ease = [0.22, 1, 0.36, 1] as const;
const views = [
  { id: "raw", label: "Your statement" },
  { id: "spendly", label: "In Spendly" },
] as const;

function mask(raw: string) {
  return raw.replace(/\d{9,}/g, (d) => `XXXX${d.slice(-4)}`).replace(/[\w.]+@[\w.]+/g, "[upi-id]");
}

export function BeforeAfter() {
  const [view, setView] = useState<(typeof views)[number]["id"]>("raw");

  return (
    <section aria-labelledby="problem-title" className="relative border-y border-line/60 bg-ink-2 py-24 sm:py-32">
      <div className="mx-auto grid max-w-7xl grid-cols-1 gap-14 px-5 sm:px-8 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
        <div>
          <SectionHeading
            id="problem-title"
            eyebrow="From raw to readable"
            title={<>Your statement shows what happened.<br className="hidden sm:block" /> <span className="text-fg/55">Spendly helps explain why.</span></>}
            body="Bank and UPI statements are written for ledgers, not people. Spendly cleans every line, masks the identifiers, names the merchant, and knows that moving money between your own accounts isn't spending."
          />
          <Reveal delay={0.1}>
            <ul className="mt-8 space-y-3 text-[0.95rem] text-muted">
              {[
                "Merchant names cleaned from UPI and card strings",
                "Transfers and card-bill payments kept out of spending",
                "Refunds recognised, subscriptions spotted",
                "Every change visible and correctable",
              ].map((t) => (
                <li key={t} className="flex gap-3">
                  <span className="mt-2.5 h-1 w-3 shrink-0 rounded-full bg-lime/70" aria-hidden="true" />
                  {t}
                </li>
              ))}
            </ul>
          </Reveal>
        </div>

        <Reveal y={24}>
          <div className="glass rounded-2xl p-2">
            <div className="flex items-center justify-between gap-3 p-2">
              <div role="tablist" aria-label="Compare the raw statement with Spendly" className="flex rounded-xl border border-line bg-ink p-1">
                {views.map((v) => (
                  <button
                    key={v.id}
                    role="tab"
                    type="button"
                    id={`tab-${v.id}`}
                    aria-selected={view === v.id}
                    aria-controls="compare-panel"
                    onClick={() => setView(v.id)}
                    className={`relative whitespace-nowrap rounded-lg px-3.5 py-2 text-[0.82rem] transition-colors ${
                      view === v.id ? "text-ink" : "text-muted hover:text-fg"
                    }`}
                  >
                    {view === v.id ? (
                      <motion.span layoutId="tab-pill" className="absolute inset-0 rounded-lg bg-lime" transition={{ duration: 0.35, ease }} />
                    ) : null}
                    <span className="relative font-medium">{v.label}</span>
                  </button>
                ))}
              </div>
              <span className="hidden sm:block"><SyntheticBadge /></span>
            </div>

            <div id="compare-panel" role="tabpanel" aria-labelledby={`tab-${view}`} className="min-h-[360px] p-2">
              <AnimatePresence mode="wait" initial={false}>
                {view === "raw" ? (
                  <motion.ul
                    key="raw"
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -8 }}
                    transition={{ duration: 0.3, ease }}
                    className="space-y-2"
                  >
                    {rawToStructured.map((r) => (
                      <li key={r.raw} className="flex items-center justify-between gap-4 rounded-xl border border-line bg-ink/70 px-4 py-3.5">
                        <code className="min-w-0 truncate font-mono text-[0.74rem] text-muted">{r.raw}</code>
                        <span className="tabular shrink-0 font-mono text-[0.74rem] text-fg/70">
                          {r.amount < 0 ? `${Math.abs(r.amount).toFixed(2)} Dr` : `${r.amount.toFixed(2)} Cr`}
                        </span>
                      </li>
                    ))}
                    <li className="px-2 pt-3 text-[0.8rem] text-faint">
                      Reference numbers, UPI IDs, five different formats — and no answer to “what did I spend on?”
                    </li>
                  </motion.ul>
                ) : (
                  <motion.ul
                    key="spendly"
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -8 }}
                    transition={{ duration: 0.3, ease }}
                    className="space-y-2"
                  >
                    {rawToStructured.map((r, i) => (
                      <motion.li
                        key={r.raw}
                        initial={{ opacity: 0, x: 10 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.35, delay: i * 0.05, ease }}
                        className="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1 rounded-xl border border-line bg-card px-4 py-3"
                      >
                        <div className="min-w-0">
                          <p className="truncate text-[0.9rem] font-medium text-fg">{r.merchant}</p>
                          <p className="truncate font-mono text-[0.66rem] text-faint">{mask(r.raw)}</p>
                        </div>
                        <span className={`tabular text-right text-[0.9rem] ${r.amount > 0 ? "text-down" : "text-fg"}`}>
                          {formatINR(r.amount, { sign: true })}
                        </span>
                        <div className="col-span-2 flex flex-wrap gap-1.5 pt-1">
                          <span className="rounded-md border border-line px-1.5 py-0.5 text-[0.66rem] text-muted">{r.category}</span>
                          <span className={`rounded-md px-1.5 py-0.5 text-[0.66rem] ${
                            r.type === "Expense" ? "border border-line text-muted" : "bg-lime/10 text-lime"
                          }`}>{r.type}</span>
                        </div>
                      </motion.li>
                    ))}
                  </motion.ul>
                )}
              </AnimatePresence>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
