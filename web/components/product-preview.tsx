import {
  ArrowDownRight, ArrowUpRight, BarChart3, FileCheck2, LayoutDashboard, Receipt, Repeat, Upload,
} from "lucide-react";
import { categories, formatINR, months, transactions } from "@/lib/demo-data";
import { CategoryBars, MonthColumns } from "./charts";
import { CountUp } from "./count-up";
import { Reveal } from "./reveal";
import { SectionHeading, SyntheticBadge } from "./section-heading";

const pages = [
  { icon: LayoutDashboard, label: "Overview", active: true },
  { icon: Receipt, label: "Transactions" },
  { icon: BarChart3, label: "Spending Insights" },
  { icon: Repeat, label: "Recurring Payments" },
  { icon: FileCheck2, label: "Data Quality" },
  { icon: Upload, label: "Import" },
];

const kpis = [
  { label: "Expenditure", value: 40088, note: "September 2026" },
  { label: "Income received", value: 65220, note: "salary & interest" },
  { label: "Net cash flow", value: 18382, note: "excl. own-account transfers" },
];

const insights = [
  { tone: "down", text: "Spending fell 60.8% vs August. The biggest drop was in Shopping (−₹57,468)." },
  { tone: "up", text: "Groceries rose by ₹1,360 (+24%)." },
  { tone: "neutral", text: "6 recurring payments cost about ₹21,190 a month (estimated)." },
];

export function ProductPreview() {
  return (
    <section id="product" aria-labelledby="product-title" className="relative py-24 sm:py-32">
      <div className="mx-auto max-w-7xl px-5 sm:px-8">
        <SectionHeading
          id="product-title"
          eyebrow="The product"
          title="More than a list of transactions."
          body="Spendly reads your statement, cleans every line and turns it into a dashboard that answers real questions: where the money went, what changed, and what repeats."
        />

        <Reveal className="mt-14" y={30}>
          <div className="glass relative overflow-hidden rounded-3xl shadow-[0_60px_120px_-50px_rgb(0_0_0/0.9)]">
            <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-lime/40 to-transparent" />
            <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
              <div className="flex items-center gap-2 text-[0.8rem] text-muted">
                <span className="text-fg">Spendly</span>
                <span className="hidden text-faint sm:inline">/</span> <span className="hidden sm:inline">Overview</span>
              </div>
              <SyntheticBadge />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-[210px_1fr]">
              {/* sidebar mirrors the real app's six pages */}
              <aside className="hidden border-r border-line p-4 lg:block" aria-label="App pages (preview)">
                <ul className="space-y-1">
                  {pages.map(({ icon: Icon, label, active }) => (
                    <li key={label}
                      className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-[0.8rem] ${
                        active ? "bg-white/[0.05] text-fg" : "text-muted"
                      }`}>
                      <Icon className={`h-4 w-4 ${active ? "text-lime" : "text-faint"}`} aria-hidden="true" />
                      {label}
                    </li>
                  ))}
                </ul>
              </aside>

              <div className="space-y-5 p-4 sm:p-6">
                <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                  {kpis.map((k) => (
                    <div key={k.label} className="rounded-xl border border-line bg-ink-2/70 p-4">
                      <p className="eyebrow text-[0.6rem]">{k.label}</p>
                      <CountUp value={k.value} as="inr"
                        className="tabular mt-1.5 block text-xl font-semibold tracking-tight text-fg sm:text-2xl" />
                      <p className="mt-1 text-[0.7rem] text-faint">{k.note}</p>
                    </div>
                  ))}
                  <div className="rounded-xl border border-line bg-ink-2/70 p-4">
                    <p className="eyebrow text-[0.6rem]">Month over month</p>
                    <p className="tabular mt-1.5 flex items-center gap-1 text-xl font-semibold tracking-tight text-down sm:text-2xl">
                      <ArrowDownRight className="h-5 w-5" aria-hidden="true" />60.8%
                    </p>
                    <p className="mt-1 text-[0.7rem] text-faint">Sep vs Aug</p>
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1.4fr_1fr]">
                  <div className="rounded-xl border border-line bg-ink-2/70 p-5">
                    <div className="mb-5 flex items-baseline justify-between">
                      <p className="text-sm font-medium text-fg">Six-month spending</p>
                      <p className="eyebrow text-[0.6rem]">Apr – Sep 2026</p>
                    </div>
                    <MonthColumns data={months} />
                  </div>
                  <div className="rounded-xl border border-line bg-ink-2/70 p-5">
                    <p className="mb-4 text-sm font-medium text-fg">Where it went · September</p>
                    <CategoryBars items={categories} max={6} />
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1.4fr_1fr]">
                  <div className="rounded-xl border border-line bg-ink-2/70 p-5">
                    <p className="mb-3 text-sm font-medium text-fg">Recent transactions</p>
                    <table className="w-full text-left text-[0.8rem]">
                      <caption className="sr-only">Recent synthetic transactions</caption>
                      <thead>
                        <tr className="eyebrow text-[0.6rem]">
                          <th scope="col" className="pb-2 font-normal">Date</th>
                          <th scope="col" className="pb-2 font-normal">Merchant</th>
                          <th scope="col" className="hidden pb-2 font-normal sm:table-cell">Category</th>
                          <th scope="col" className="pb-2 text-right font-normal">Amount</th>
                        </tr>
                      </thead>
                      <tbody>
                        {transactions.map((t) => (
                          <tr key={t.merchant + t.date} className="border-t border-line/70">
                            <td className="py-2.5 pr-3 whitespace-nowrap text-faint">{t.date}</td>
                            <td className="py-2.5 pr-3 text-fg">{t.merchant}</td>
                            <td className="hidden py-2.5 pr-3 text-muted sm:table-cell">{t.category}</td>
                            <td className={`tabular py-2.5 text-right ${t.amount > 0 ? "text-down" : "text-fg/85"}`}>
                              {formatINR(t.amount, { sign: true })}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="rounded-xl border border-line bg-ink-2/70 p-5">
                    <p className="mb-3 text-sm font-medium text-fg">Insights</p>
                    <ul className="space-y-2.5">
                      {insights.map((i) => (
                        <li key={i.text} className="flex gap-3 rounded-lg border border-line/80 bg-card/60 p-3 text-[0.8rem] leading-snug text-fg/85">
                          {i.tone === "down" ? <ArrowDownRight className="mt-0.5 h-4 w-4 shrink-0 text-down" aria-hidden="true" />
                            : i.tone === "up" ? <ArrowUpRight className="mt-0.5 h-4 w-4 shrink-0 text-up" aria-hidden="true" />
                            : <Repeat className="mt-0.5 h-4 w-4 shrink-0 text-lime-2" aria-hidden="true" />}
                          {i.text}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
