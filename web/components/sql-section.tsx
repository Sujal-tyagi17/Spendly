"use client";

import { AnimatePresence, motion } from "motion/react";
import { Database } from "lucide-react";
import { useState } from "react";
import { Reveal } from "./reveal";
import { SectionHeading } from "./section-heading";

const ease = [0.22, 1, 0.36, 1] as const;

/* Simplified excerpts of the real queries in the repository's sql/ folder. */
const queries = [
  {
    id: "mom",
    label: "Month over month",
    file: "sql/monthly_summary.sql",
    plain: "Compares each month with the one before — and never divides by zero.",
    sql: `SELECT month_start,
       expenditure_paise,
       LAG(expenditure_paise) OVER (ORDER BY month_start) AS prev_month,
       CASE WHEN LAG(expenditure_paise) OVER (ORDER BY month_start) > 0
            THEN ROUND(100.0 * (expenditure_paise
                 - LAG(expenditure_paise) OVER (ORDER BY month_start))
                 / LAG(expenditure_paise) OVER (ORDER BY month_start), 1)
       END AS mom_change_pct
FROM filled;`,
  },
  {
    id: "category",
    label: "Category share",
    file: "sql/category_spending.sql",
    plain: "Each category's share of total spending, ranked.",
    sql: `SELECT category,
       expenditure_paise,
       ROUND(100.0 * expenditure_paise
             / NULLIF(SUM(expenditure_paise) OVER (), 0), 1) AS share_pct,
       RANK() OVER (ORDER BY expenditure_paise DESC)       AS spend_rank
FROM spend
ORDER BY expenditure_paise DESC;`,
  },
  {
    id: "merchants",
    label: "Merchant ranking",
    file: "sql/top_merchants.sql",
    plain: "Where most of your money actually goes.",
    sql: `SELECT normalized_merchant AS merchant,
       COUNT(*)            AS transaction_count,
       SUM(amount_paise)   AS expenditure_paise,
       RANK() OVER (ORDER BY SUM(amount_paise) DESC) AS spend_rank
FROM base
WHERE transaction_type = 'expense' AND direction = 'debit'
GROUP BY normalized_merchant
LIMIT :limit;`,
  },
  {
    id: "recurring",
    label: "Recurring payments",
    file: "sql/recurring_candidates.sql",
    plain: "Days between payments to the same merchant — the raw signal for subscriptions.",
    sql: `SELECT merchant, transaction_date, amount_paise,
       CAST(julianday(transaction_date)
            - julianday(LAG(transaction_date) OVER (
                  PARTITION BY merchant ORDER BY transaction_date))
            AS INTEGER) AS days_since_previous
FROM payments
WHERE occurrences >= :min_occurrences;`,
  },
] as const;

const KEYWORDS =
  /\b(SELECT|FROM|WHERE|AND|AS|CASE|WHEN|THEN|END|OVER|ORDER|BY|PARTITION|GROUP|LIMIT|DESC|ROUND|LAG|RANK|SUM|COUNT|NULLIF|CAST|INTEGER|julianday)\b/g;

function highlight(sql: string) {
  return sql.split("\n").map((line, i) => {
    const parts: React.ReactNode[] = [];
    let last = 0;
    for (const match of line.matchAll(KEYWORDS)) {
      const start = match.index ?? 0;
      if (start > last) parts.push(line.slice(last, start));
      parts.push(<span key={start} className="text-lime-2">{match[0]}</span>);
      last = start + match[0].length;
    }
    parts.push(line.slice(last));
    return (
      <span key={i} className="block">
        <span className="mr-4 inline-block w-5 select-none text-right text-faint/70" aria-hidden="true">{i + 1}</span>
        {parts}
      </span>
    );
  });
}

const capabilities = [
  ["Month-over-month analysis", "Equal-length periods, partial months labelled"],
  ["Category comparisons", "Share of spend and what changed"],
  ["Merchant rankings", "Who receives most of your money"],
  ["Recurring payment detection", "Interval + amount stability"],
];

export function SqlSection() {
  const [active, setActive] = useState<(typeof queries)[number]["id"]>("mom");
  const query = queries.find((q) => q.id === active)!;

  return (
    <section aria-labelledby="sql-title" className="relative py-24 sm:py-32">
      <div className="mx-auto grid max-w-7xl grid-cols-1 gap-14 px-5 sm:px-8 lg:grid-cols-[0.85fr_1.15fr] lg:items-center">
        <div>
          <SectionHeading
            id="sql-title"
            eyebrow="Under the hood"
            title={<>SQL-powered intelligence.</>}
            body="Every number on the dashboard comes from documented SQL — CTEs, window functions and recursive queries running on a local SQLite database. Each metric is defined once, so it means the same thing on every page."
          />
          <Reveal delay={0.1}>
            <dl className="mt-9 grid gap-px overflow-hidden rounded-2xl border border-line bg-line sm:grid-cols-2">
              {capabilities.map(([title, desc]) => (
                <div key={title} className="bg-card p-5">
                  <dt className="text-[0.95rem] font-medium text-fg">{title}</dt>
                  <dd className="mt-1 text-[0.82rem] text-muted">{desc}</dd>
                </div>
              ))}
            </dl>
          </Reveal>
        </div>

        <Reveal y={24}>
          <div className="glass overflow-hidden rounded-2xl">
            <div role="tablist" aria-label="Example queries" className="flex gap-1 overflow-x-auto border-b border-line p-2">
              {queries.map((q) => (
                <button
                  key={q.id}
                  role="tab"
                  type="button"
                  id={`sql-tab-${q.id}`}
                  aria-selected={active === q.id}
                  aria-controls="sql-panel"
                  onClick={() => setActive(q.id)}
                  className={`shrink-0 rounded-lg px-3 py-2 text-[0.8rem] whitespace-nowrap transition-colors ${
                    active === q.id ? "bg-white/[0.07] text-fg" : "text-muted hover:text-fg"
                  }`}
                >
                  {q.label}
                </button>
              ))}
            </div>
            <div id="sql-panel" role="tabpanel" aria-labelledby={`sql-tab-${query.id}`}>
              <div className="flex items-center gap-2 border-b border-line/70 px-5 py-2.5 font-mono text-[0.7rem] text-faint">
                <Database className="h-3.5 w-3.5" aria-hidden="true" />
                {query.file}
                <span className="ml-auto">simplified excerpt</span>
              </div>
              <AnimatePresence mode="wait" initial={false}>
                <motion.div
                  key={query.id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.2, ease }}
                >
                  <pre className="min-h-[15rem] overflow-x-auto px-5 py-5 font-mono text-[0.76rem] leading-[1.7] text-fg/80">
                    <code>{highlight(query.sql)}</code>
                  </pre>
                  <p className="border-t border-line/70 px-5 py-3.5 text-[0.82rem] text-muted">
                    <span className="text-fg">In plain words:</span> {query.plain}
                  </p>
                </motion.div>
              </AnimatePresence>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
