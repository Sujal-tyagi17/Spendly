import { Loader2 } from "lucide-react";
import Link from "next/link";
import { forwardRef } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

const variants: Record<Variant, string> = {
  primary: "bg-lime text-ink hover:bg-[#d4ff80] shadow-[0_0_0_1px_rgb(198_255_94/0.35)]",
  secondary: "border border-line bg-white/[0.03] text-fg hover:border-line-2 hover:bg-white/[0.06]",
  ghost: "text-muted hover:bg-white/[0.05] hover:text-fg",
  danger: "border border-err/40 bg-err/10 text-[#ffb4ab] hover:bg-err/20",
};
const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-[0.8rem] gap-1.5 rounded-lg",
  md: "h-10 px-4 text-sm gap-2 rounded-xl",
};

export function buttonClass(variant: Variant = "secondary", size: Size = "md", extra = "") {
  return `inline-flex shrink-0 items-center justify-center font-medium whitespace-nowrap select-none transition-[background-color,border-color,color,box-shadow] duration-200 disabled:pointer-events-none disabled:opacity-45 ${variants[variant]} ${sizes[size]} ${extra}`;
}

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", loading = false, className = "", children, disabled, type = "button", ...rest },
  ref,
) {
  return (
    <button ref={ref} type={type} disabled={disabled || loading} aria-busy={loading || undefined}
      className={buttonClass(variant, size, className)} {...rest}>
      {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
      {children}
    </button>
  );
});

export function ButtonLink({ href, variant = "secondary", size = "md", className = "", children }: {
  href: string; variant?: Variant; size?: Size; className?: string; children: React.ReactNode;
}) {
  return <Link href={href} className={buttonClass(variant, size, className)}>{children}</Link>;
}
