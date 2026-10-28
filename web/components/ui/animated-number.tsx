"use client";

import { animate, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";

/**
 * Counts up only the first time a value appears (first page load). Later
 * changes — e.g. a filter tweak — update instantly, so numbers don't keep
 * re-animating.
 */
export function AnimatedNumber({ value, format }: { value: number; format: (n: number) => string }) {
  const reduced = useReducedMotion();
  const done = useRef(false);
  const [display, setDisplay] = useState<number | null>(null);

  useEffect(() => {
    if (done.current || reduced) {
      done.current = true;
      setDisplay(null);
      return;
    }
    done.current = true;
    const controls = animate(0, value, {
      duration: 0.9,
      ease: [0.22, 1, 0.36, 1],
      onUpdate: (v) => setDisplay(v),
      onComplete: () => setDisplay(null),
    });
    return () => controls.stop();
  }, [value, reduced]);

  return (
    <>
      <span aria-hidden="true">{format(display ?? value)}</span>
      <span className="sr-only">{format(value)}</span>
    </>
  );
}
