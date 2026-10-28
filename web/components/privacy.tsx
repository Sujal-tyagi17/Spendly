import { EyeOff, FileX2, KeyRound, ScrollText, Sparkles, Trash2 } from "lucide-react";
import { Reveal, RevealItem, Stagger } from "./reveal";
import { SectionHeading } from "./section-heading";

/* Every statement below is backed by the Python code and its tests:
   src/pdf_parser.py, src/privacy.py, src/database.py, src/ai.py, tests/test_privacy.py */
const items = [
  {
    icon: FileX2,
    title: "PDFs are never stored",
    body: "Statements are read in memory and discarded after parsing. Only the extracted transactions are saved.",
  },
  {
    icon: EyeOff,
    title: "Identifiers masked before saving",
    body: "Long account, card and reference numbers become XXXX1234. UPI IDs and phone numbers are replaced before anything reaches the database.",
  },
  {
    icon: ScrollText,
    title: "Nothing sensitive in logs",
    body: "Spendly logs counts and statuses only — never transaction descriptions. A redacting log filter backs this up.",
  },
  {
    icon: KeyRound,
    title: "Passwords used once",
    body: "A statement password opens the file and is never written anywhere.",
  },
  {
    icon: Sparkles,
    title: "AI is optional and off by default",
    body: "If you switch it on, only sanitised merchant names or already-computed summaries are sent — never amounts, balances or account details.",
  },
  {
    icon: Trash2,
    title: "Delete everything, anytime",
    body: "One action removes every imported statement, transaction and decision from your database.",
  },
];

export function Privacy() {
  return (
    <section id="privacy" aria-labelledby="privacy-title" className="relative overflow-hidden border-y border-line/60 bg-ink-2 py-24 sm:py-32">
      <div aria-hidden="true" className="pointer-events-none absolute -bottom-40 left-1/2 h-80 w-[60rem] -translate-x-1/2 rounded-full bg-lime/[0.05] blur-3xl" />
      <div className="relative mx-auto max-w-7xl px-5 sm:px-8">
        <SectionHeading
          id="privacy-title"
          eyebrow="Privacy"
          title="Your statement is personal. Spendly treats it that way."
          body="Here is exactly what happens to your data — nothing more, nothing less."
        />
        <Stagger className="mt-14 grid gap-px overflow-hidden rounded-2xl border border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <RevealItem key={item.title} className="bg-card p-6 transition-colors duration-300 hover:bg-card-2 sm:p-7">
              <item.icon className="h-5 w-5 text-lime-2" aria-hidden="true" />
              <h3 className="mt-5 text-[1.05rem] font-semibold tracking-tight text-fg">{item.title}</h3>
              <p className="mt-2 text-[0.9rem] leading-relaxed text-muted">{item.body}</p>
            </RevealItem>
          ))}
        </Stagger>
        <Reveal delay={0.1}>
          <p className="mt-6 max-w-3xl text-[0.82rem] leading-relaxed text-faint">
            Where processing happens depends on where Spendly runs: on your own computer when you run it locally, or on
            the server hosting the app when you use a hosted version — where each visitor&apos;s data lives only in that
            session&apos;s memory. Locally, imported transactions sit in an unencrypted SQLite file on your machine, and
            masking is pattern-based, so unusual identifier formats could slip through.
          </p>
        </Reveal>
      </div>
    </section>
  );
}
