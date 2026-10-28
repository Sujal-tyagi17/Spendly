import { AlertTriangle, ArrowDownLeft, ArrowLeftRight, ArrowUpRight, CheckCircle2, CircleDot, CreditCard, CopyX, RotateCcw, Sparkles, Tag } from "lucide-react";
import { TYPE_LABELS } from "@/lib/format";

const chip = "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[0.7rem] font-medium whitespace-nowrap";

export function CategoryBadge({ category }: { category: string }) {
  const muted = category === "Other";
  return (
    <span className={`${chip} ${muted ? "border-line text-muted" : "border-line-2 bg-white/[0.03] text-fg/85"}`}>
      <Tag className="h-3 w-3 text-faint" aria-hidden="true" />
      {category}
    </span>
  );
}

/** Transaction type with an icon + text label (never colour alone). */
export function TypeBadge({ type }: { type: string }) {
  const map: Record<string, { icon: React.ComponentType<{ className?: string }>; cls: string }> = {
    expense: { icon: ArrowUpRight, cls: "border-line text-muted" },
    income: { icon: ArrowDownLeft, cls: "border-pos/30 bg-pos/10 text-pos" },
    refund: { icon: RotateCcw, cls: "border-pos/30 bg-pos/5 text-pos" },
    transfer: { icon: ArrowLeftRight, cls: "border-info/30 bg-info/10 text-info" },
    cc_repayment: { icon: CreditCard, cls: "border-info/30 bg-info/10 text-info" },
    other: { icon: CircleDot, cls: "border-line text-muted" },
  };
  const { icon: Icon, cls } = map[type] ?? map.other;
  return (
    <span className={`${chip} ${cls}`}>
      <Icon className="h-3 w-3" aria-hidden="true" />
      {TYPE_LABELS[type] ?? type}
    </span>
  );
}

export function StatusBadge({ status, duplicate, method }: { status: string; duplicate?: boolean; method?: string }) {
  if (duplicate) {
    return <span className={`${chip} border-warn/35 bg-warn/10 text-warn`}><CopyX className="h-3 w-3" aria-hidden="true" />Possible duplicate</span>;
  }
  if (status === "needs_review") {
    return (
      <span className={`${chip} border-warn/35 bg-warn/10 text-warn`}>
        {method === "ai" ? <Sparkles className="h-3 w-3" aria-hidden="true" /> : <AlertTriangle className="h-3 w-3" aria-hidden="true" />}
        {method === "none" ? "Uncategorized" : method === "ai" ? "AI suggestion" : "Review"}
      </span>
    );
  }
  if (status === "reviewed") {
    return <span className={`${chip} border-line text-muted`}><CheckCircle2 className="h-3 w-3 text-pos" aria-hidden="true" />Reviewed</span>;
  }
  return <span className={`${chip} border-transparent text-faint`}><CheckCircle2 className="h-3 w-3" aria-hidden="true" />OK</span>;
}

export function Pill({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "lime" | "warn" | "pos" | "neg" }) {
  const tones = {
    neutral: "border-line text-muted",
    lime: "border-lime/30 bg-lime/10 text-lime",
    warn: "border-warn/35 bg-warn/10 text-warn",
    pos: "border-pos/30 bg-pos/10 text-pos",
    neg: "border-neg/30 bg-neg/10 text-neg",
  };
  return <span className={`${chip} ${tones[tone]}`}>{children}</span>;
}
