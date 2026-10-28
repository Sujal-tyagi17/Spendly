import { Reveal } from "./reveal";

export function SectionHeading({
  eyebrow,
  title,
  body,
  align = "left",
  id,
}: {
  eyebrow: string;
  title: React.ReactNode;
  body?: React.ReactNode;
  align?: "left" | "center";
  id?: string;
}) {
  const centered = align === "center";
  return (
    <Reveal className={centered ? "mx-auto max-w-3xl text-center" : "max-w-3xl"}>
      <p className={`eyebrow mb-4 flex items-center gap-2 ${centered ? "justify-center" : "justify-start"}`}>
        <span className="h-px w-6 bg-lime/60" aria-hidden="true" />
        {eyebrow}
      </p>
      <h2 id={id} className="text-balance text-[2.1rem] leading-[1.05] font-semibold tracking-[-0.035em] text-fg sm:text-5xl">
        {title}
      </h2>
      {body ? <p className={`mt-5 text-[1.05rem] leading-relaxed text-muted ${centered ? "mx-auto" : ""} max-w-2xl`}>{body}</p> : null}
    </Reveal>
  );
}

export function SyntheticBadge({ className = "" }: { className?: string }) {
  return (
    <span className={`eyebrow inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-md border border-line bg-ink/60 px-2 py-1 text-[0.625rem] ${className}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-muted" aria-hidden="true" />
      Illustrative · synthetic data
    </span>
  );
}
