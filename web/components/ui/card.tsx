export function Card({ className = "", children, as: Tag = "section", ...rest }: React.HTMLAttributes<HTMLElement> & {
  as?: "section" | "div" | "article";
}) {
  return (
    <Tag className={`rounded-2xl border border-line bg-card transition-colors duration-200 ${className}`} {...rest}>
      {children}
    </Tag>
  );
}

export function SectionHeader({ title, subtitle, action, id, level = 2 }: {
  title: React.ReactNode; subtitle?: React.ReactNode; action?: React.ReactNode; id?: string; level?: 2 | 3;
}) {
  const H = level === 2 ? "h2" : "h3";
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <H id={id} className="text-[0.95rem] font-semibold tracking-tight text-fg">{title}</H>
        {subtitle ? <p className="mt-0.5 text-[0.8rem] text-muted">{subtitle}</p> : null}
      </div>
      {action ? <div className="flex items-center gap-2">{action}</div> : null}
    </div>
  );
}

export function PageIntro({ children }: { children: React.ReactNode }) {
  return <p className="max-w-3xl text-[0.92rem] leading-relaxed text-muted">{children}</p>;
}
