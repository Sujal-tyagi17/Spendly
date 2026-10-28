"use client";

import { animate, useInView, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { formatINR } from "@/lib/demo-data";

const formats = {
  inr: (n: number) => formatINR(n),
  number: (n: number) => Math.round(n).toLocaleString("en-IN"),
} as const;

/** Counts up to `value` once in view. Reduced motion → shows the final value immediately. */
export function CountUp({
  value,
  as = "number",
  duration = 1.4,
  delay = 0,
  className,
}: {
  value: number;
  /** Serializable format name, so Server Components can use this too. */
  as?: keyof typeof formats;
  duration?: number;
  delay?: number;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true });
  const reduced = useReducedMotion();
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    if (!inView) return;
    if (reduced) {
      // Set after hydration (not during render) so server and client markup match.
      const id = requestAnimationFrame(() => setDisplay(value));
      return () => cancelAnimationFrame(id);
    }
    const controls = animate(0, value, {
      duration,
      delay,
      ease: [0.22, 1, 0.36, 1],
      onUpdate: (latest) => setDisplay(latest),
    });
    return () => controls.stop();
  }, [inView, reduced, value, duration, delay]);

  const format = formats[as];
  const shown = display;
  return (
    <span ref={ref} className={className}>
      {/* Screen readers always get the final value, never the in-between numbers. */}
      <span aria-hidden="true">{format(shown)}</span>
      <span className="sr-only">{format(value)}</span>
    </span>
  );
}
