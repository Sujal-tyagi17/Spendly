"use client";

/**
 * "Skip to content". Next.js keeps the previous route mounted (hidden) during client
 * navigation, so two elements can share id="main"; this jumps to the visible one.
 */
export function SkipLink() {
  return (
    <a
      href="#main"
      onClick={(e) => {
        const target = [...document.querySelectorAll<HTMLElement>("main")].find((m) => m.offsetParent !== null);
        if (!target) return;
        e.preventDefault();
        target.setAttribute("tabindex", "-1");
        target.focus();
        target.scrollIntoView();
      }}
      className="sr-only z-[70] rounded-lg bg-lime px-4 py-2 font-medium text-ink focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
    >
      Skip to content
    </a>
  );
}
