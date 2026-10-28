"use client";

import { AnimatePresence, motion } from "motion/react";
import {
  BarChart3, ChevronsLeft, ChevronsRight, Database, FileCheck2, FlaskConical, LayoutDashboard, Lock, Menu, Receipt,
  PiggyBank, Repeat, Sigma, Upload, X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useApp } from "@/lib/store";
import { LogoMark } from "../logo";
import { buttonClass } from "../ui/button";
import { Toaster } from "../ui/toaster";
import { ActiveFilterChips, DateRangeSelector, FilterButton } from "./filters";

export const NAV = [
  { href: "/app", label: "Overview", icon: LayoutDashboard, filters: true },
  { href: "/app/transactions", label: "Transactions", icon: Receipt, filters: true },
  { href: "/app/insights", label: "Spending Insights", icon: BarChart3, filters: true },
  { href: "/app/recurring", label: "Recurring Payments", icon: Repeat, filters: true },
  { href: "/app/budgets", label: "Budget Planner", icon: PiggyBank, filters: false },
  { href: "/app/analysis", label: "SQL Analysis", icon: Sigma, filters: true },
  { href: "/app/quality", label: "Data Quality", icon: FileCheck2, filters: false },
  { href: "/app/import", label: "Import & Settings", icon: Upload, filters: false },
] as const;

function DataSourceSwitch({ compact = false }: { compact?: boolean }) {
  const { mode, setMode } = useApp();
  if (compact) {
    return (
      <button type="button" onClick={() => setMode(mode === "demo" ? "user" : "demo")}
        title={mode === "demo" ? "Demo data (synthetic) — switch to My data" : "My data — switch to Demo data"}
        aria-label={mode === "demo" ? "Viewing demo data. Switch to my data" : "Viewing my data. Switch to demo data"}
        className="flex h-10 w-10 items-center justify-center rounded-xl border border-line text-muted hover:text-fg">
        {mode === "demo" ? <FlaskConical className="h-4 w-4 text-warn" aria-hidden="true" /> : <Database className="h-4 w-4 text-lime" aria-hidden="true" />}
      </button>
    );
  }
  return (
    <div>
      <p className="eyebrow mb-2 text-[0.6rem]">Data source</p>
      <div role="radiogroup" aria-label="Data source" className="grid grid-cols-2 rounded-xl border border-line bg-ink p-1">
        {(["demo", "user"] as const).map((m) => (
          <button key={m} type="button" role="radio" aria-checked={mode === m} onClick={() => mode !== m && setMode(m)}
            className={`relative rounded-lg px-2 py-1.5 text-[0.78rem] font-medium transition-colors ${mode === m ? "text-ink" : "text-muted hover:text-fg"}`}>
            {mode === m ? <motion.span layoutId="mode-pill" className="absolute inset-0 rounded-lg bg-lime" transition={{ duration: 0.25 }} /> : null}
            <span className="relative">{m === "demo" ? "Demo" : "My data"}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function PrivacyStatus() {
  const { meta, mode } = useApp();
  const text = !meta ? "Connecting…"
    : meta.storage === "memory" ? "Private to this browser session"
    : mode === "demo" ? "Synthetic sample data"
    : "Stored on this computer (SQLite)";
  return (
    <div className="rounded-xl border border-line bg-ink-2/70 p-3">
      <p className="flex items-center gap-2 text-[0.75rem] text-fg/90">
        <Lock className="h-3.5 w-3.5 text-lime-2" aria-hidden="true" />{text}
      </p>
      <p className="mt-1 text-[0.7rem] leading-relaxed text-faint">PDFs are never stored. AI {meta?.ai.enabled ? "is on" : "is off"}.</p>
    </div>
  );
}

function NavLinks({ collapsed = false, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <ul className="space-y-1">
      {NAV.map((item) => {
        const active = item.href === "/app" ? pathname === "/app" : pathname.startsWith(item.href);
        const Icon = item.icon;
        return (
          <li key={item.href}>
            <Link href={item.href} onClick={onNavigate} aria-current={active ? "page" : undefined}
              title={collapsed ? item.label : undefined}
              className={`group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-[0.86rem] transition-colors ${
                active ? "bg-white/[0.06] text-fg" : "text-muted hover:bg-white/[0.03] hover:text-fg"} ${collapsed ? "justify-center px-0" : ""}`}>
              {active ? <span className="absolute top-2 bottom-2 left-0 w-[3px] rounded-full bg-lime" aria-hidden="true" /> : null}
              <Icon className={`h-[18px] w-[18px] shrink-0 ${active ? "text-lime" : "text-faint group-hover:text-muted"}`} aria-hidden="true" />
              <span className={collapsed ? "sr-only" : "truncate"}>{item.label}</span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { mode, setMode, meta, metaError } = useApp();
  const [collapsed, setCollapsed] = useState(false);
  const [drawer, setDrawer] = useState(false);

  useEffect(() => {
    try {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restore UI preference once
      setCollapsed(window.localStorage.getItem("spendly.sidebar") === "collapsed");
    } catch {}
  }, []);
  const toggleCollapse = () => {
    setCollapsed((c) => {
      try { window.localStorage.setItem("spendly.sidebar", c ? "open" : "collapsed"); } catch {}
      return !c;
    });
  };

  const current = NAV.find((n) => (n.href === "/app" ? pathname === "/app" : pathname.startsWith(n.href))) ?? NAV[0];

  return (
    <div className="min-h-dvh bg-ink text-fg">

      {/* ---------- desktop sidebar */}
      <aside aria-label="Spendly navigation"
        className={`fixed inset-y-0 left-0 z-40 hidden flex-col border-r border-line bg-ink-2 transition-[width] duration-300 ease-out-soft lg:flex ${collapsed ? "w-[76px]" : "w-[248px]"}`}>
        <div className={`flex h-16 items-center ${collapsed ? "justify-center" : "px-5"}`}>
          <Link href="/" className="flex items-center gap-2.5 rounded-lg" aria-label="Spendly home">
            <LogoMark className="h-7 w-7" />
            {!collapsed ? <span className="text-[1.02rem] font-semibold tracking-tight">Spendly</span> : null}
          </Link>
        </div>
        <nav aria-label="App pages" className={`flex-1 overflow-y-auto pt-2 ${collapsed ? "px-3" : "px-3"}`}>
          <NavLinks collapsed={collapsed} />
        </nav>
        <div className={`space-y-3 border-t border-line p-3 ${collapsed ? "flex flex-col items-center" : ""}`}>
          {collapsed ? <DataSourceSwitch compact /> : <><DataSourceSwitch /><PrivacyStatus /></>}
          <button type="button" onClick={toggleCollapse} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className={`flex h-9 items-center gap-2 rounded-lg px-2 text-[0.78rem] text-faint transition-colors hover:text-fg ${collapsed ? "w-10 justify-center" : "w-full"}`}>
            {collapsed ? <ChevronsRight className="h-4 w-4" aria-hidden="true" /> : <><ChevronsLeft className="h-4 w-4" aria-hidden="true" />Collapse</>}
          </button>
        </div>
      </aside>

      {/* ---------- mobile top bar + drawer */}
      <div className="sticky top-0 z-40 flex h-14 items-center justify-between border-b border-line bg-ink/90 px-4 backdrop-blur-md lg:hidden">
        <Link href="/" className="flex items-center gap-2" aria-label="Spendly home">
          <LogoMark className="h-7 w-7" /><span className="font-semibold">Spendly</span>
        </Link>
        <button type="button" onClick={() => setDrawer(true)} aria-label="Open navigation" aria-expanded={drawer}
          className="flex h-10 w-10 items-center justify-center rounded-xl border border-line"><Menu className="h-5 w-5" aria-hidden="true" /></button>
      </div>
      <AnimatePresence>
        {drawer ? (
          <motion.div className="fixed inset-0 z-[70] lg:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <div className="absolute inset-0 bg-black/70" onClick={() => setDrawer(false)} aria-hidden="true" />
            <motion.nav aria-label="App pages" initial={{ x: "-100%" }} animate={{ x: 0 }} exit={{ x: "-100%" }}
              transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
              className="absolute inset-y-0 left-0 flex w-[82%] max-w-[300px] flex-col border-r border-line bg-ink-2 p-4">
              <div className="mb-4 flex items-center justify-between">
                <span className="flex items-center gap-2"><LogoMark className="h-7 w-7" /><span className="font-semibold">Spendly</span></span>
                <button type="button" onClick={() => setDrawer(false)} aria-label="Close navigation" className="flex h-10 w-10 items-center justify-center rounded-xl border border-line">
                  <X className="h-5 w-5" aria-hidden="true" />
                </button>
              </div>
              <NavLinks onNavigate={() => setDrawer(false)} />
              <div className="mt-auto space-y-3 pt-4"><DataSourceSwitch /><PrivacyStatus /></div>
            </motion.nav>
          </motion.div>
        ) : null}
      </AnimatePresence>

      {/* ---------- main column */}
      <div className={`transition-[padding] duration-300 ease-out-soft ${collapsed ? "lg:pl-[76px]" : "lg:pl-[248px]"}`}>
        <header className="border-b border-line/70 bg-ink/80 backdrop-blur-md lg:sticky lg:top-0 lg:z-30">
          <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6 lg:min-h-16 lg:px-8">
            <div className="flex min-w-0 items-center gap-3">
              <h1 className="truncate text-xl font-semibold tracking-[-0.02em] sm:text-[1.4rem]">{current.label}</h1>
              <span className={`hidden items-center gap-1.5 rounded-md border px-2 py-0.5 text-[0.68rem] font-medium sm:inline-flex ${
                mode === "demo" ? "border-warn/35 bg-warn/10 text-warn" : "border-lime/30 bg-lime/10 text-lime"}`}>
                {mode === "demo" ? <FlaskConical className="h-3 w-3" aria-hidden="true" /> : <Lock className="h-3 w-3" aria-hidden="true" />}
                {mode === "demo" ? "Demo · synthetic" : "My data"}
              </span>
            </div>
            <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto">
              {current.filters ? <><DateRangeSelector /><FilterButton /></> : null}
              <Link href="/app/import" className={buttonClass("primary", "md", "ml-auto sm:ml-0")}>
                <Upload className="h-4 w-4" aria-hidden="true" /> Import statement
              </Link>
            </div>
          </div>
          {current.filters ? (
            <div className="mx-auto max-w-[1400px] px-4 sm:px-6 lg:px-8 [&:has(>div)]:pb-3"><ActiveFilterChips /></div>
          ) : null}
        </header>

        {mode === "demo" && meta ? (
          <div className="mx-auto max-w-[1400px] px-4 pt-4 sm:px-6 lg:px-8">
            <div className="flex flex-col gap-2 rounded-xl border border-warn/25 bg-warn/[0.06] px-4 py-2.5 text-[0.8rem] text-fg/85 sm:flex-row sm:items-center sm:justify-between">
              <span><span className="font-medium text-warn">Demo mode.</span> You&apos;re exploring synthetic sample data. It isn&apos;t anyone&apos;s real money.</span>
              <button type="button" onClick={() => setMode("user")} className="self-start text-[0.78rem] font-medium text-lime underline-offset-2 hover:underline sm:self-auto">
                Switch to my data
              </button>
            </div>
          </div>
        ) : null}

        <main id="main" className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          {metaError ? (
            <div role="alert" className="mb-6 rounded-2xl border border-err/30 bg-err/5 p-4 text-[0.88rem]">
              <p className="font-medium text-fg">The Spendly API isn&apos;t reachable.</p>
              <p className="mt-1 text-muted">Start it with <code className="rounded bg-white/5 px-1.5 py-0.5 font-mono text-[0.8rem]">uvicorn api.main:app --port 8000</code> from the project folder, then refresh. ({metaError})</p>
            </div>
          ) : null}
          <motion.div key={pathname + mode} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}>
            {children}
          </motion.div>
        </main>
      </div>
      <Toaster />
    </div>
  );
}
