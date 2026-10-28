"use client";

import { motion } from "motion/react";
import { ArrowLeftRight, CalendarClock, PieChart, ScanSearch } from "lucide-react";
import { amazonPayments, categories, formatCompactINR, formatINR, recurring } from "@/lib/demo-data";
import { RevealItem, Stagger } from "./reveal";
import { SectionHeading } from "./section-heading";

const ease = [0.22, 1, 0.36, 1] as const;

function Card({
  icon: Icon,
  index,
  title,
  body,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  index: string;
  title: string;
  body: string;
  children: React.ReactNode;
}) {
  return (
    <RevealItem className="h-full">
      <motion.article
        whileHover={{ y: -4 }}
        transition={{ duration: 0.3, ease }}
        className="group relative flex h-full flex-col overflow-hidden rounded-2xl border border-line bg-card p-6 transition-colors duration-300 hover:border-line-2 sm:p-7"
      >
        <div aria-hidden="true"
          className="pointer-events-none absolute -top-24 -right-24 h-48 w-48 rounded-full bg-lime/0 blur-3xl transition-colors duration-500 group-hover:bg-lime/[0.07]" />
        <div className="mb-6 flex items-center justify-between">
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-line bg-ink-2 text-lime-2">
            <Icon className="h-5 w-5" aria-hidden="true" />
          </span>
          <span className="font-mono text-[0.7rem] text-faint">{index}</span>
        </div>
        <h3 className="text-xl font-semibold tracking-tight text-fg">{title}</h3>
        <p className="mt-2 text-[0.95rem] leading-relaxed text-muted">{body}</p>
        <div className="mt-7 flex-1 rounded-xl border border-line/80 bg-ink-2/80 p-4">{children}</div>
      </motion.article>
    </RevealItem>
  );
}

function SpendingVisual() {
  const total = categories.reduce((s, c) => s + c.amount, 0);
  return (
    <div>
      <div className="flex h-3 w-full overflow-hidden rounded-full" role="img"
        aria-label={`September spending split: ${categories.map((c) => `${c.name} ${c.share}%`).join(", ")}`}>
        {categories.map((c, i) => (
          <div key={c.name} style={{ width: `${(c.amount / total) * 100}%` }}
            className={`h-full border-r-2 border-ink-2 last:border-r-0 transition-opacity duration-300 group-hover:opacity-100 ${
              i === 0 ? "bg-lime" : i === 1 ? "bg-lime-2/70" : "bg-white/[0.14]"} ${i > 1 ? "opacity-70" : ""}`} />
        ))}
      </div>
      <ul className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-[0.75rem]">
        {categories.slice(0, 4).map((c) => (
          <li key={c.name} className="flex justify-between gap-2">
            <span className="truncate text-muted">{c.name}</span>
            <span className="tabular text-fg/85">{c.share}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function RecurringVisual() {
  const monthly = recurring.reduce((s, r) => s + r.amount, 0);
  return (
    <div>
      <ul className="space-y-1.5">
        {recurring.slice(0, 4).map((r) => (
          <li key={r.merchant} className="flex items-center justify-between text-[0.78rem]">
            <span className="flex items-center gap-2 text-fg/85">
              <span className="h-1.5 w-1.5 rounded-full bg-lime-2" aria-hidden="true" />
              {r.merchant}
            </span>
            <span className="tabular text-muted">{formatINR(r.amount)}/mo</span>
          </li>
        ))}
      </ul>
      <div className="mt-3 flex items-baseline justify-between border-t border-line pt-3 text-[0.78rem]">
        <span className="text-faint">6 payments · estimated</span>
        <span className="tabular text-fg">
          {formatINR(monthly)}/mo
          <span className="ml-2 text-faint transition-colors duration-300 group-hover:text-lime">≈ {formatINR(monthly * 12)}/yr</span>
        </span>
      </div>
    </div>
  );
}

function UnusualVisual() {
  const max = Math.max(...amazonPayments);
  return (
    <div>
      <div className="relative h-16" role="img"
        aria-label="Six Amazon payments; one of ₹54,999 is far above the others, which are under ₹3,000">
        <div className="absolute inset-x-0 top-1/2 h-px bg-line" aria-hidden="true" />
        {amazonPayments.map((amount, i) => {
          const outlier = amount === max;
          const left = Math.sqrt(amount / max) * 92 + 2;
          return (
            <span key={i} style={{ left: `${left}%` }}
              className={`absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full ${
                outlier ? "h-3.5 w-3.5 bg-up ring-4 ring-up/20 transition-[box-shadow] duration-300 group-hover:ring-8"
                  : "h-2.5 w-2.5 bg-white/30"}`} />
          );
        })}
      </div>
      <p className="text-[0.78rem] leading-snug text-muted">
        <span className="text-fg">{formatINR(max)} at Amazon</span> is 28× your median Amazon payment. Flagged with a
        reason, never called fraud.
      </p>
    </div>
  );
}

const changes = [
  { name: "Groceries", delta: 1360 },
  { name: "Transport", delta: -290 },
  { name: "Food & Dining", delta: -5525 },
  { name: "Shopping", delta: -57468 },
];

function ChangeVisual() {
  const max = Math.max(...changes.map((c) => Math.abs(c.delta)));
  return (
    <ul className="space-y-2" aria-label="Category change, September vs August (synthetic)">
      {changes.map((c, i) => {
        const width = Math.max(3, Math.sqrt(Math.abs(c.delta) / max) * 50);
        return (
          <li key={c.name} className="grid grid-cols-[6.5rem_1fr_4.2rem] items-center gap-2 text-[0.74rem]">
            <span className="truncate text-muted">{c.name}</span>
            <span className="relative h-2" aria-hidden="true">
              <span className="absolute left-1/2 top-[-3px] h-[14px] w-px bg-line-2" />
              <motion.span
                className={`absolute top-0 h-2 rounded-full ${c.delta > 0 ? "left-1/2 bg-up/80" : "right-1/2 bg-down/80"}`}
                initial={{ width: 0 }}
                whileInView={{ width: `${width}%` }}
                viewport={{ once: true }}
                transition={{ duration: 0.8, delay: 0.2 + i * 0.08, ease }}
              />
            </span>
            <span className={`tabular text-right ${c.delta > 0 ? "text-up" : "text-down"}`}>
              {c.delta > 0 ? "+" : "−"}{formatCompactINR(Math.abs(c.delta))}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export function Features() {
  return (
    <section id="features" aria-labelledby="features-title" className="relative py-24 sm:py-32">
      <div className="mx-auto max-w-7xl px-5 sm:px-8">
        <SectionHeading
          id="features-title"
          eyebrow="Features"
          title="Four questions your statement can't answer."
          body="Each one is computed from your own transactions with transparent rules — no black boxes, no invented numbers. Examples below use synthetic data."
        />
        <Stagger className="mt-14 grid gap-5 md:grid-cols-2">
          <Card icon={PieChart} index="01" title="Understand your spending"
            body="See where every rupee went by category and merchant, with transfers and card-bill payments kept out so nothing is counted twice.">
            <SpendingVisual />
          </Card>
          <Card icon={CalendarClock} index="02" title="Find recurring payments"
            body="Spendly finds payments that repeat on a schedule — even when the date drifts or the price changes — and estimates what they cost a year.">
            <RecurringVisual />
          </Card>
          <Card icon={ScanSearch} index="03" title="Spot unusual transactions"
            body="Payments far above your usual amount at the same merchant or in the same category are flagged, each with a plain-English reason.">
            <UnusualVisual />
          </Card>
          <Card icon={ArrowLeftRight} index="04" title="Track what changes month to month"
            body="Not just “you spent more” — which categories and merchants drove the change, compared over equal-length periods.">
            <ChangeVisual />
          </Card>
        </Stagger>
      </div>
    </section>
  );
}
