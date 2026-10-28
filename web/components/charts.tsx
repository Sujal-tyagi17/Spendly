"use client";

import { motion } from "motion/react";
import { useId } from "react";
import { formatCompactINR, formatINR, type Month } from "@/lib/demo-data";

/** Smooth-ish line through points using a gentle cardinal curve. */
function pathFor(points: [number, number][]) {
  if (points.length < 2) return "";
  let d = `M ${points[0][0]} ${points[0][1]}`;
  for (let i = 0; i < points.length - 1; i++) {
    const [x0, y0] = points[i - 1] ?? points[i];
    const [x1, y1] = points[i];
    const [x2, y2] = points[i + 1];
    const [x3, y3] = points[i + 2] ?? points[i + 1];
    const t = 0.18;
    d += ` C ${x1 + (x2 - x0) * t} ${y1 + (y2 - y0) * t}, ${x2 - (x3 - x1) * t} ${y2 - (y3 - y1) * t}, ${x2} ${y2}`;
  }
  return d;
}

export function SpendLine({
  data,
  height = 120,
  showAxis = true,
  delay = 0.2,
}: {
  data: Month[];
  height?: number;
  showAxis?: boolean;
  delay?: number;
}) {
  const id = useId().replace(/:/g, "");
  const width = 320;
  const padX = 10;
  const top = 14;
  const bottom = showAxis ? 22 : 8;
  const max = Math.max(...data.map((d) => d.spend)) * 1.08;
  const pts: [number, number][] = data.map((d, i) => [
    padX + (i * (width - padX * 2)) / (data.length - 1),
    top + (1 - d.spend / max) * (height - top - bottom),
  ]);
  const line = pathFor(pts);
  const area = `${line} L ${pts[pts.length - 1][0]} ${height - bottom} L ${pts[0][0]} ${height - bottom} Z`;
  const last = pts[pts.length - 1];

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="h-auto w-full overflow-visible"
      role="img"
      aria-label={`Monthly spending, ${data.map((d) => `${d.label} ${formatINR(d.spend)}`).join(", ")} (synthetic data)`}
    >
      <defs>
        <linearGradient id={`fill-${id}`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#c6ff5e" stopOpacity="0.16" />
          <stop offset="100%" stopColor="#c6ff5e" stopOpacity="0" />
        </linearGradient>
      </defs>
      {[0.25, 0.5, 0.75].map((f) => (
        <line key={f} x1={padX} x2={width - padX} y1={top + f * (height - top - bottom)}
          y2={top + f * (height - top - bottom)} stroke="#1e261e" strokeWidth="1" />
      ))}
      <motion.path
        d={area}
        fill={`url(#fill-${id})`}
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true }}
        transition={{ duration: 0.8, delay: delay + 0.9 }}
      />
      <motion.path
        d={line}
        fill="none"
        stroke="#c6ff5e"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        initial={{ pathLength: 0 }}
        whileInView={{ pathLength: 1 }}
        viewport={{ once: true }}
        transition={{ duration: 1.4, delay, ease: [0.65, 0, 0.35, 1] }}
      />
      <motion.circle
        cx={last[0]} cy={last[1]} r="4" fill="#c6ff5e" stroke="#0d100d" strokeWidth="2"
        initial={{ scale: 0, opacity: 0 }}
        whileInView={{ scale: 1, opacity: 1 }}
        viewport={{ once: true }}
        transition={{ duration: 0.3, delay: delay + 1.35 }}
      />
      {showAxis
        ? data.map((d, i) => (
            <text key={d.label} x={pts[i][0]} y={height - 4} textAnchor="middle" fill="#5f675d"
              fontSize="9" fontFamily="var(--font-geist-mono)">
              {d.label}
            </text>
          ))
        : null}
    </svg>
  );
}

export function CategoryBars({
  items,
  max = 4,
  delay = 0.3,
}: {
  items: { name: string; amount: number; share: number }[];
  max?: number;
  delay?: number;
}) {
  const top = items.slice(0, max);
  const largest = Math.max(...top.map((i) => i.amount));
  return (
    <ul className="space-y-2.5">
      {top.map((item, i) => (
        <li key={item.name}>
          <div className="mb-1 flex items-baseline justify-between text-[0.72rem]">
            <span className="text-fg/85">{item.name}</span>
            <span className="tabular text-muted">{formatCompactINR(item.amount)}</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.05]">
            <motion.div
              className={`h-full rounded-full ${i === 0 ? "bg-lime" : "bg-lime-2/45"}`}
              initial={{ width: 0 }}
              whileInView={{ width: `${(item.amount / largest) * 100}%` }}
              viewport={{ once: true }}
              transition={{ duration: 0.9, delay: delay + i * 0.08, ease: [0.22, 1, 0.36, 1] }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Vertical columns for the six-month trend in the product preview. */
export function MonthColumns({ data, delay = 0.2 }: { data: Month[]; delay?: number }) {
  const max = Math.max(...data.map((d) => d.spend));
  return (
    <div className="flex h-44 items-end gap-3 sm:gap-4" role="img"
      aria-label={`Six-month spending: ${data.map((d) => `${d.label} ${formatINR(d.spend)}`).join(", ")} (synthetic data)`}>
      {data.map((d, i) => {
        const peak = d.spend === max;
        return (
          <div key={d.label} className="flex h-full flex-1 flex-col items-center justify-end gap-2">
            <span className={`tabular text-[0.65rem] ${peak ? "text-fg" : "text-faint"}`}>{formatCompactINR(d.spend)}</span>
            <div className="flex w-full flex-1 items-end justify-center">
              <motion.div
                className={`w-full max-w-9 rounded-t-md ${peak ? "bg-lime" : "bg-white/[0.09]"}`}
                initial={{ height: 0 }}
                whileInView={{ height: `${(d.spend / max) * 100}%` }}
                viewport={{ once: true }}
                transition={{ duration: 0.8, delay: delay + i * 0.07, ease: [0.22, 1, 0.36, 1] }}
              />
            </div>
            <span className="eyebrow text-[0.6rem]">{d.label}</span>
          </div>
        );
      })}
    </div>
  );
}
