import { ArrowUpRight, ArrowDown } from "lucide-react";
import Link from "next/link";
import { isExternalAppUrl, site } from "@/lib/site";

const base =
  "group inline-flex items-center justify-center gap-2 rounded-xl px-5 h-12 text-[0.95rem] font-medium " +
  "transition-[background-color,border-color,color,box-shadow] duration-300 ease-out-soft select-none";

/** Primary CTA — opens the Spendly app (/app by default, or NEXT_PUBLIC_APP_URL). */
export function ExploreButton({ className = "", label = "Explore Spendly", demo = false }: { className?: string; label?: string; demo?: boolean }) {
  const href = demo ? `${site.appUrl}?mode=demo` : site.appUrl;
  const classes = `${base} bg-lime text-ink hover:bg-[#d4ff80] shadow-[0_0_0_1px_rgb(198_255_94/0.4),0_10px_30px_-12px_rgb(198_255_94/0.55)] ${className}`;
  const arrow = (
    <ArrowUpRight
      aria-hidden="true"
      className="h-4 w-4 transition-transform duration-300 ease-out-soft group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
    />
  );
  if (isExternalAppUrl) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" className={classes}>
        {label}
        {arrow}
        <span className="sr-only">(opens the Spendly app in a new tab)</span>
      </a>
    );
  }
  return (
    <Link href={href} className={classes}>
      {label}
      {arrow}
    </Link>
  );
}

export function SecondaryButton({ href, children, className = "" }: { href: string; children: React.ReactNode; className?: string }) {
  return (
    <a
      href={href}
      className={`${base} hairline bg-white/[0.02] text-fg hover:border-line-2 hover:bg-white/[0.05] ${className}`}
    >
      {children}
      <ArrowDown
        aria-hidden="true"
        className="h-4 w-4 text-muted transition-transform duration-300 ease-out-soft group-hover:translate-y-0.5"
      />
    </a>
  );
}
