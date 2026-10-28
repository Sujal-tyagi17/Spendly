"use client";

import { motion, useMotionValue, useReducedMotion, useSpring, useTransform } from "motion/react";
import { Sparkles, TrendingDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { categories, currentMonth, formatINR, months, transactions } from "@/lib/demo-data";
import { CategoryBars, SpendLine } from "./charts";
import { CountUp } from "./count-up";
import { SyntheticBadge } from "./section-heading";

const ease = [0.22, 1, 0.36, 1] as const;

function useFinePointer() {
  const [fine, setFine] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(pointer: fine) and (min-width: 1024px)");
    const update = () => setFine(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return fine;
}

export function HeroDashboard() {
  const ref = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  const fine = useFinePointer();
  const tilt = fine && !reduced;

  const px = useMotionValue(0);
  const py = useMotionValue(0);
  const rotateY = useSpring(useTransform(px, [-0.5, 0.5], [-4, 4]), { stiffness: 120, damping: 20 });
  const rotateX = useSpring(useTransform(py, [-0.5, 0.5], [3, -3]), { stiffness: 120, damping: 20 });

  const onMove = (e: React.PointerEvent) => {
    if (!tilt || !ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    px.set((e.clientX - rect.left) / rect.width - 0.5);
    py.set((e.clientY - rect.top) / rect.height - 0.5);
  };
  const onLeave = () => {
    px.set(0);
    py.set(0);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 40, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 1, delay: 0.35, ease }}
      className="relative mx-auto w-full max-w-[560px] [perspective:1400px]"
    >
      {/* soft light pool behind the composition */}
      <div aria-hidden="true" className="absolute -inset-10 -z-10 rounded-full bg-[radial-gradient(closest-side,rgb(198_255_94/0.12),transparent)] blur-2xl" />

      <motion.div
        ref={ref}
        onPointerMove={onMove}
        onPointerLeave={onLeave}
        style={tilt ? { rotateX, rotateY, transformStyle: "preserve-3d" } : undefined}
        className="float-slow sm:pb-40"
      >
        {/* ---------- main panel */}
        <div className="glass relative rounded-2xl p-5 shadow-[0_40px_80px_-30px_rgb(0_0_0/0.8)] sm:p-6">
          <div className="mb-5 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-lime" aria-hidden="true" />
              <span className="text-[0.8rem] font-medium text-fg/90">Overview</span>
              <span className="text-[0.8rem] text-faint">· {currentMonth.label}</span>
            </div>
          </div>

          <div className="grid gap-5 sm:grid-cols-[1.35fr_1fr]">
            <div>
              <p className="eyebrow text-[0.6rem]">Spent this month</p>
              <div className="mt-1.5 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <CountUp
                  value={currentMonth.spend}
                  as="inr"
                  delay={0.6}
                  className="tabular text-[2rem] font-semibold tracking-tight text-fg"
                />
                <span className="inline-flex items-center gap-1 rounded-md bg-down/10 px-1.5 py-0.5 text-[0.7rem] font-medium text-down">
                  <TrendingDown className="h-3 w-3" aria-hidden="true" />
                  {Math.abs(currentMonth.changePct)}% vs Aug
                </span>
              </div>
              <div className="mt-4">
                <SpendLine data={months} delay={0.7} />
              </div>
            </div>
            <div className="sm:border-l sm:border-line sm:pl-5">
              <p className="eyebrow mb-3 text-[0.6rem]">By category</p>
              <CategoryBars items={categories} delay={0.9} />
            </div>
          </div>
        </div>

        {/* ---------- recent transactions (offset, layered) */}
        <div
          className="glass relative mt-4 rounded-2xl p-4 sm:absolute sm:top-[calc(100%-11.75rem)] sm:-left-8 sm:mt-0 sm:w-[300px] sm:shadow-[0_30px_60px_-25px_rgb(0_0_0/0.9)]"
          style={tilt ? { transform: "translateZ(40px)" } : undefined}
        >
          <p className="eyebrow mb-2.5 text-[0.6rem]">Recent</p>
          <ul className="space-y-1">
            {transactions.slice(0, 3).map((t, i) => (
              <motion.li
                key={t.merchant + t.date}
                initial={{ opacity: 0, x: -12 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.5, delay: 1.2 + i * 0.15, ease }}
                className="flex items-center justify-between rounded-lg px-2 py-1.5 transition-colors hover:bg-white/[0.03]"
              >
                <div className="min-w-0">
                  <p className="truncate text-[0.8rem] text-fg">{t.merchant}</p>
                  <p className="text-[0.66rem] text-faint">{t.date} · {t.category}</p>
                </div>
                <span className={`tabular ml-3 text-[0.8rem] ${t.amount > 0 ? "text-down" : "text-fg/80"}`}>
                  {formatINR(t.amount, { sign: true })}
                </span>
              </motion.li>
            ))}
          </ul>
        </div>

        {/* ---------- insight card */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 1.7, ease }}
          className="insight-glow relative mt-4 rounded-2xl border border-lime/25 bg-[#121a10]/95 p-4 sm:absolute sm:-right-6 sm:-top-16 sm:mt-0 sm:w-[250px]"
          style={tilt ? { transform: "translateZ(60px)" } : undefined}
        >
          <p className="eyebrow mb-1.5 flex items-center gap-1.5 text-[0.6rem] text-lime">
            <Sparkles className="h-3 w-3" aria-hidden="true" /> Insight
          </p>
          <p className="text-[0.82rem] leading-snug text-fg/90">
            August&apos;s spike came from one purchase: <span className="text-fg">₹54,999 at Amazon</span>, 28× your
            usual Amazon payment.
          </p>
        </motion.div>
      </motion.div>
      <div className="mt-6 flex justify-center sm:absolute sm:right-0 sm:bottom-6 sm:mt-0">
        <SyntheticBadge />
      </div>
    </motion.div>
  );
}
