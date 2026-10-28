import { InfoTip } from "./info-tip";

export function MetricCard({ label, value, note, tip, emphasis = false, delta }: {
  label: string;
  value: React.ReactNode;
  note?: React.ReactNode;
  tip?: React.ReactNode;
  emphasis?: boolean;
  delta?: React.ReactNode;
}) {
  return (
    <div className={`relative flex min-h-[7.5rem] flex-col rounded-2xl border p-4 sm:p-5 ${
      emphasis ? "border-lime/25 bg-[linear-gradient(180deg,rgb(198_255_94/0.06),rgb(17_21_17)_60%)]" : "border-line bg-card"}`}>
      <div className="flex items-center gap-1">
        <p className="eyebrow text-[0.62rem]">{label}</p>
        {tip ? <InfoTip label={label}>{tip}</InfoTip> : null}
      </div>
      <div className="tabular mt-2 text-[1.6rem] leading-none font-semibold tracking-tight text-fg sm:text-[1.85rem]">{value}</div>
      <div className="mt-auto flex flex-wrap items-center gap-2 pt-3 text-[0.75rem] text-muted">
        {delta}
        {note ? <span>{note}</span> : null}
      </div>
    </div>
  );
}
