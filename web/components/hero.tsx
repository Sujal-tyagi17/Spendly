"use client";

import { motion } from "motion/react";
import { ShieldCheck } from "lucide-react";
import { ExploreButton, SecondaryButton } from "./cta";
import { HeroDashboard } from "./hero-dashboard";

const ease = [0.22, 1, 0.36, 1] as const;
const lines = ["Your money has a story.", "It's time to read it."];

export function Hero() {
  return (
    <section id="top" aria-labelledby="hero-title" className="relative overflow-hidden pt-32 pb-20 sm:pt-40 lg:pb-24">
      <div aria-hidden="true" className="atmosphere pointer-events-none absolute inset-0" />
      <div aria-hidden="true" className="grid-fade pointer-events-none absolute inset-0" />

      <div className="relative mx-auto grid max-w-7xl grid-cols-1 items-center gap-16 px-5 sm:px-8 lg:grid-cols-[1.15fr_1fr] lg:gap-10">
        <div className="max-w-2xl">
          <motion.p
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease }}
            className="eyebrow mb-6 flex items-center gap-2.5"
          >
            <span className="h-px w-8 bg-lime" aria-hidden="true" />
            Personal finance intelligence
          </motion.p>

          <h1
            id="hero-title"
            className="text-[2.6rem] leading-[1] font-semibold tracking-[-0.045em] text-fg sm:text-[3.6rem] lg:text-[2.95rem] xl:text-[3.6rem]"
          >
            {lines.map((line, i) => (
              <span key={line} className="block overflow-hidden pb-[0.08em]">
                <motion.span
                  className={`block ${i === 1 ? "text-fg/55" : ""}`}
                  initial={{ y: "105%" }}
                  animate={{ y: 0 }}
                  transition={{ duration: 0.9, delay: 0.1 + i * 0.14, ease }}
                >
                  {line}
                </motion.span>
              </span>
            ))}
          </h1>

          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.8, delay: 0.5 }}
            className="mt-7 max-w-[34rem] text-[1.08rem] leading-relaxed text-muted"
          >
            Turn your bank statements into a clearer picture of your spending. Discover patterns, understand your
            habits, and make every rupee count.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.65, ease }}
            className="mt-9 flex flex-col gap-3 sm:flex-row"
          >
            <ExploreButton demo label="Try the demo" />
            <SecondaryButton href="#how-it-works">See how it works</SecondaryButton>
          </motion.div>

          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.8, delay: 0.9 }}
            className="mt-8 flex items-start gap-2.5 text-[0.82rem] leading-relaxed text-faint"
          >
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-lime-2" aria-hidden="true" />
            The demo opens with synthetic transactions, so no upload is needed. Statements are read in memory and never stored. Account numbers and UPI IDs are masked before anything is
            saved.
          </motion.p>
        </div>

        <div className="lg:pl-6">
          <HeroDashboard />
        </div>
      </div>
    </section>
  );
}
