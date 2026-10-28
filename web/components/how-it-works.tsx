import { FileUp, ListChecks, LineChart, Info } from "lucide-react";
import { Reveal, RevealItem, Stagger } from "./reveal";
import { SectionHeading } from "./section-heading";

const steps = [
  {
    icon: FileUp,
    title: "Upload your statement",
    body: "Drop in a text-based PDF from your bank or PhonePe. Password-protected statements work — the password is used once to open the file and never stored.",
    meta: "PDF · up to 10 MB",
  },
  {
    icon: ListChecks,
    title: "Review and verify",
    body: "Preview every row before import. Spendly checks running balances, skips exact duplicates, and flags anything uncertain so you stay in control.",
    meta: "Preview · balance check · duplicates",
  },
  {
    icon: LineChart,
    title: "Explore your insights",
    body: "See spending by category and merchant, month-over-month changes, recurring payments and unusual transactions. Correct any category in a click.",
    meta: "6 views · CSV export",
  },
];

export function HowItWorks() {
  return (
    <section id="how-it-works" aria-labelledby="how-title" className="relative border-y border-line/60 bg-ink-2 py-24 sm:py-32">
      <div className="mx-auto max-w-7xl px-5 sm:px-8">
        <SectionHeading id="how-title" eyebrow="How it works" title="Three steps from PDF to clarity." />

        <Stagger className="relative mt-14 grid gap-5 lg:grid-cols-3" gap={0.12} role="list" aria-label="Steps">
          <div aria-hidden="true" className="absolute top-[3.25rem] right-[16%] left-[16%] hidden h-px bg-gradient-to-r from-line via-lime/30 to-line lg:block" />
          {steps.map((step, i) => (
            <RevealItem key={step.title} role="listitem">
                <div className="relative flex h-full flex-col rounded-2xl border border-line bg-card p-6 transition-colors duration-300 hover:border-line-2 sm:p-7">
                  <div className="flex items-center gap-4">
                    <span className="relative z-10 inline-flex h-12 w-12 items-center justify-center rounded-xl border border-line-2 bg-ink text-lime">
                      <step.icon className="h-5 w-5" aria-hidden="true" />
                    </span>
                    <span className="font-mono text-sm text-faint">Step {String(i + 1).padStart(2, "0")}</span>
                  </div>
                  <h3 className="mt-6 text-xl font-semibold tracking-tight text-fg">{step.title}</h3>
                  <p className="mt-2 flex-1 text-[0.95rem] leading-relaxed text-muted">{step.body}</p>
                  <p className="eyebrow mt-6 text-[0.62rem]">{step.meta}</p>
                </div>
            </RevealItem>
          ))}
        </Stagger>

        <Reveal delay={0.1}>
          <div className="mt-8 flex gap-3 rounded-2xl border border-line bg-card/60 p-5 text-[0.9rem] leading-relaxed text-muted">
            <Info className="mt-0.5 h-4 w-4 shrink-0 text-lime-2" aria-hidden="true" />
            <p>
              <span className="text-fg">Supported formats today:</span> text-based bank statements laid out as a table
              (Date · Description · Debit · Credit · Balance) and PhonePe-style statements. Scanned or photographed PDFs
              aren&apos;t supported yet, and not every bank&apos;s layout is recognised — if yours isn&apos;t, Spendly says so
              instead of guessing.
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
