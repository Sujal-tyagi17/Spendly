"use client";

import { CheckCircle2, EyeOff, FlaskConical, ScanSearch } from "lucide-react";
import { useState } from "react";
import { useApi } from "@/lib/api";
import { fmtDate, inr } from "@/lib/format";
import type { Anomaly, AnomalyEvaluation, AnomalyInfo, InsightLink } from "@/lib/types";
import { Pill } from "../ui/badges";
import { Button } from "../ui/button";
import { Card, SectionHeader } from "../ui/card";
import { EmptyState } from "../ui/states";

const DEVIATION = {
  notable: { label: "Notable deviation", tone: "neutral" as const },
  large: { label: "Large deviation", tone: "warn" as const },
  extreme: { label: "Extreme deviation", tone: "neg" as const },
};

const METHOD_SHORT: Record<string, string> = {
  robust_z_prior: "Robust z-score vs earlier payments",
  iqr_prior: "IQR vs earlier payments",
  iqr_full: "IQR on full history",
  rule: "Category threshold",
};

function Stat({ k, v }: { k: string; v: React.ReactNode }) {
  return <div><dt className="text-[0.7rem] text-faint">{k}</dt><dd className="tabular text-[0.82rem] text-fg/90">{v}</dd></div>;
}

function AnomalyCard({ a, busy, onReview, onOpen }: {
  a: Anomaly; busy: boolean; onReview: (id: number, s: "dismissed" | "expected") => void; onOpen: (l: InsightLink) => void;
}) {
  const dev = DEVIATION[a.deviation] ?? DEVIATION.notable;
  const reference = a.basis === "merchant" ? `${a.reference_count} earlier ${a.reference_label} payments`
    : a.basis === "category" ? `${a.reference_count} earlier ${a.reference_label} payments` : `${a.reference_label} threshold`;
  return (
    <Card as="article" className="flex h-full flex-col p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-[0.95rem] font-semibold text-fg">{a.merchant}</p>
          <p className="text-[0.75rem] text-faint">{fmtDate(a.transaction_date)} · {a.category}</p>
        </div>
        <div className="text-right">
          <p className="tabular text-lg font-semibold text-fg">{inr(a.amount_paise)}</p>
          <Pill tone={dev.tone}>{dev.label}</Pill>
        </div>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
        <Stat k="Method" v={METHOD_SHORT[a.method] ?? a.method} />
        <Stat k="Compared with" v={reference} />
        <Stat k="Their median" v={a.median_paise === null ? "—" : inr(a.median_paise)} />
        <Stat k="Deviation" v={a.robust_z !== null ? `z ${a.robust_z} · ${a.ratio_to_median}× median`
          : a.ratio_to_median !== null ? `${a.ratio_to_median}× median` : "—"} />
      </dl>
      <p className="mt-3 flex-1 text-[0.84rem] leading-relaxed text-fg/80">{a.reason}</p>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        {a.review_status === "new" ? (
          <>
            <Button size="sm" onClick={() => onReview(a.id, "expected")} loading={busy}><CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />I expected this</Button>
            <Button size="sm" variant="ghost" onClick={() => onReview(a.id, "dismissed")} disabled={busy}><EyeOff className="h-3.5 w-3.5" aria-hidden="true" />Dismiss</Button>
          </>
        ) : <Pill>{a.review_status === "expected" ? "Marked expected" : "Dismissed"}</Pill>}
        <Button size="sm" variant="ghost" className="ml-auto" onClick={() => onOpen({ start: a.transaction_date, end: a.transaction_date, merchants: [a.merchant] })}>
          View transaction
        </Button>
      </div>
    </Card>
  );
}

function Evaluation({ method }: { method: string }) {
  const { data } = useApi<AnomalyEvaluation>("/api/anomalies/evaluation", []);
  if (!data) return null;
  const f = (v: number | null) => (v === null ? "n/a" : v.toFixed(2));
  return (
    <details className="rounded-2xl border border-line bg-card p-4 text-[0.82rem]">
      <summary className="flex cursor-pointer items-center gap-2 text-fg"><FlaskConical className="h-4 w-4 text-lime-2" aria-hidden="true" />How well does this work? (synthetic evaluation)</summary>
      <p className="mt-3 leading-relaxed text-muted">
        Measured on a generated 12-month account with {data.dataset.anomalies} anomalies injected by a script. Results are for the held-out
        second half ({fmtDate(data.test_period[0])} – {fmtDate(data.test_period[1])}). These are <b className="font-medium text-fg/90">synthetic labels, not fraud labels</b>,
        so they show how the methods compare, not how often a real flag matters.
      </p>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[520px] text-left text-[0.8rem]">
          <thead className="border-b border-line text-[0.7rem] text-muted"><tr>
            {["Method", "Precision", "Recall", "F1", "F1 on 5 other seeds"].map((h, i) => <th key={h} scope="col" className={`py-2 pr-4 font-medium ${i ? "text-right" : ""}`}>{h}</th>)}
          </tr></thead>
          <tbody>{data.results.map((r) => (
            <tr key={r.method} className="border-b border-line/50 last:border-0">
              <td className="py-2 pr-4 text-fg">{METHOD_SHORT[r.method] ?? r.method}{r.method === method ? <span className="ml-1.5 text-[0.68rem] text-lime">in use</span> : null}</td>
              <td className="tabular py-2 pr-4 text-right">{f(r.test_default.precision)}</td>
              <td className="tabular py-2 pr-4 text-right">{f(r.test_default.recall)}</td>
              <td className="tabular py-2 pr-4 text-right">{f(r.test_default.f1)}</td>
              <td className="tabular py-2 pr-4 text-right">{f(r.seeds.f1.mean)} ± {f(r.seeds.f1.sd)}</td>
            </tr>))}</tbody>
        </table>
      </div>
      <p className="mt-3 leading-relaxed text-faint">
        The full-history method looks at later payments, so its score is optimistic. No method looks for unusually small payments.
        Genuine big purchases get flagged too. That&apos;s why every flag can be marked as expected. Full write-up: docs/ANOMALY_EVALUATION.md.
      </p>
    </details>
  );
}

export function AnomalySection({ anomalies, info, onReview, busyId, onOpen }: {
  anomalies: Anomaly[]; info: AnomalyInfo; busyId: number | null;
  onReview: (id: number, s: "dismissed" | "expected") => void; onOpen: (l: InsightLink) => void;
}) {
  const [showReviewed, setShowReviewed] = useState(false);
  const shown = anomalies.filter((a) => showReviewed || a.review_status === "new");
  const reviewed = anomalies.length - anomalies.filter((a) => a.review_status === "new").length;
  const s = info.settings;
  return (
    <section aria-labelledby="unusual-title" className="space-y-4">
      <SectionHeader id="unusual-title" title="Unusual payments"
        subtitle={`Much larger than your earlier payments at the same merchant (or category): robust z ≥ ${s.z_threshold} and at least ${s.min_ratio_to_median}× the median. Unusual doesn't mean fraudulent.`}
        action={reviewed ? (
          <Button size="sm" variant="ghost" onClick={() => setShowReviewed((v) => !v)} aria-pressed={showReviewed}>
            {showReviewed ? "Hide reviewed" : `Show reviewed (${reviewed})`}
          </Button>
        ) : null} />
      {shown.length === 0 ? (
        <EmptyState icon={ScanSearch} title="Nothing unusual in this view">
          No payment stands far above your earlier payments at that merchant or in that category.
        </EmptyState>
      ) : (
        <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {shown.map((a) => <li key={a.id}><AnomalyCard a={a} busy={busyId === a.id} onReview={onReview} onOpen={onOpen} /></li>)}
        </ul>
      )}
      <p className="text-[0.78rem] leading-relaxed text-faint">
        Checked {info.checked.toLocaleString("en-IN")} payment{info.checked === 1 ? "" : "s"} against their own history.{" "}
        {info.insufficient_history ? <>{info.insufficient_history.toLocaleString("en-IN")} couldn&apos;t be checked because there weren&apos;t yet {s.merchant_min_observations} earlier
          payments at the merchant or {s.min_observations} in the category ({Object.entries(info.skipped_categories).sort((a, b) => b[1] - a[1]).slice(0, 4).map(([c, n]) => `${c} ${n}`).join(", ")}).</> : null}
        {" "}Refunds, transfers, income and card-bill payments are never checked. Reviewing a flag doesn&apos;t change the transaction.
      </p>
      <Evaluation method={info.method} />
    </section>
  );
}
