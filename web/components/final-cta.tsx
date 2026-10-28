import { ExploreButton } from "./cta";
import { Reveal } from "./reveal";

export function FinalCta() {
  return (
    <section aria-labelledby="cta-title" className="relative overflow-hidden py-28 sm:py-40">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[radial-gradient(40rem_22rem_at_50%_60%,rgb(198_255_94/0.10),transparent_70%)]" />
      <div aria-hidden="true" className="grid-fade pointer-events-none absolute inset-0 opacity-60" />
      <Reveal className="relative mx-auto max-w-3xl px-5 text-center sm:px-8">
        <h2 id="cta-title" className="text-balance text-[2.6rem] leading-[1] font-semibold tracking-[-0.045em] text-fg sm:text-6xl lg:text-7xl">
          Know where your money goes.
        </h2>
        <p className="mx-auto mt-6 max-w-md text-[1.08rem] leading-relaxed text-muted">
          Start with your statement. Leave with a clearer picture.
        </p>
        <div className="mt-10 flex justify-center">
          <ExploreButton />
        </div>
      </Reveal>
    </section>
  );
}
