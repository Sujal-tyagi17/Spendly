/** Formatting helpers. All money arrives from the API as integer paise. */

const group = (rupees: number) => Math.abs(rupees).toLocaleString("en-IN");

export function inr(paise: number | null | undefined, opts: { decimals?: boolean; sign?: boolean } = {}): string {
  if (paise === null || paise === undefined || Number.isNaN(paise)) return "—";
  const negative = paise < 0;
  const abs = Math.abs(paise);
  const body = opts.decimals
    ? `${group(Math.floor(abs / 100))}.${String(abs % 100).padStart(2, "0")}`
    : group(Math.round(abs / 100));
  const sign = negative ? "−" : opts.sign && paise > 0 ? "+" : "";
  return `${sign}₹${body}`;
}

export function inrCompact(paise: number | null | undefined): string {
  if (paise === null || paise === undefined) return "—";
  const r = paise / 100;
  const a = Math.abs(r);
  const sign = r < 0 ? "−" : "";
  const fmt = (v: number, s: string) => `${sign}₹${v.toFixed(v >= 100 ? 0 : 1).replace(/\.0$/, "")}${s}`;
  if (a >= 1e7) return fmt(a / 1e7, "Cr");
  if (a >= 1e5) return fmt(a / 1e5, "L");
  if (a >= 1e3) return fmt(a / 1e3, "K");
  return `${sign}₹${Math.round(a)}`;
}

export function pct(value: number | null | undefined, opts: { sign?: boolean } = {}): string {
  if (value === null || value === undefined) return "—";
  const s = opts.sign && value > 0 ? "+" : value < 0 ? "−" : "";
  return `${s}${Math.abs(value).toFixed(1)}%`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-09-30" → "30 Sep 2026" (no timezone conversion — dates are calendar dates). */
export function fmtDate(iso: string | null | undefined, opts: { year?: boolean } = { year: true }): string {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return `${d} ${MONTHS[m - 1]}${opts.year === false ? "" : ` ${y}`}`;
}

export function monthLabel(iso: string): string {
  const [y, m] = iso.split("-").map(Number);
  return `${MONTHS[m - 1]} ${String(y).slice(2)}`;
}

export const TYPE_LABELS: Record<string, string> = {
  expense: "Expense",
  income: "Income",
  refund: "Refund",
  transfer: "Own transfer",
  cc_repayment: "Card bill",
  other: "Other credit",
};
