"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { EMPTY_FILTERS, type Filters, type Mode, setApiMode, useApi } from "./api";

export type Meta = {
  mode: Mode;
  public: boolean;
  date_bounds: { min: string | null; max: string | null };
  coverage: { start: string | null; end: string | null };
  categories: string[];
  transaction_types: { key: string; label: string }[];
  merchants: string[];
  counts: { transactions: number; statements: number };
  ai: { enabled: boolean; message: string };
  upload: { max_mb: number; max_pages: number; formats: string[] };
  storage: "memory" | "file" | "demo-file";
};

export type Toast = { id: number; tone: "success" | "error" | "info"; message: string };

type AppState = {
  ready: boolean;
  mode: Mode;
  setMode: (mode: Mode) => void;
  filters: Filters;
  setFilters: (f: Filters) => void;
  resetFilters: () => void;
  activeFilterCount: number;
  meta: Meta | null;
  metaError: string | null;
  /** Bump after any mutation so every page refetches from the backend. */
  version: number;
  refresh: () => void;
  toasts: Toast[];
  notify: (message: string, tone?: Toast["tone"]) => void;
  dismiss: (id: number) => void;
};

const AppContext = createContext<AppState | null>(null);

const MODE_KEY = "spendly.mode";
const filterKey = (mode: Mode) => `spendly.filters.${mode}`;

function readFilters(mode: Mode): Filters {
  try {
    const raw = window.sessionStorage.getItem(filterKey(mode));
    return raw ? { ...EMPTY_FILTERS, ...JSON.parse(raw) } : EMPTY_FILTERS;
  } catch {
    return EMPTY_FILTERS;
  }
}

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [mode, setModeState] = useState<Mode>("demo");
  const [filters, setFiltersState] = useState<Filters>(EMPTY_FILTERS);
  const [version, setVersion] = useState(0);
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    let stored: Mode = "demo";
    try {
      stored = window.localStorage.getItem(MODE_KEY) === "user" ? "user" : "demo";
      // Links from the landing page (?mode=demo) always open the synthetic demo.
      if (new URLSearchParams(window.location.search).get("mode") === "demo") {
        stored = "demo";
        window.localStorage.setItem(MODE_KEY, "demo");
      }
    } catch {}
    setApiMode(stored);
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate from storage once
    setModeState(stored);
    setFiltersState(readFilters(stored));
    setReady(true);
  }, []);

  const setFilters = useCallback(
    (f: Filters) => {
      setFiltersState(f);
      try {
        window.sessionStorage.setItem(filterKey(mode), JSON.stringify(f));
      } catch {}
    },
    [mode],
  );

  const resetFilters = useCallback(() => setFilters(EMPTY_FILTERS), [setFilters]);

  const setMode = useCallback((next: Mode) => {
    setApiMode(next);
    try {
      window.localStorage.setItem(MODE_KEY, next);
    } catch {}
    setModeState(next);
    // Switching data source clears filters, exactly like the original app.
    setFiltersState(EMPTY_FILTERS);
    setVersion((v) => v + 1);
  }, []);

  const refresh = useCallback(() => setVersion((v) => v + 1), []);

  const dismiss = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  const notify = useCallback(
    (message: string, tone: Toast["tone"] = "success") => {
      const id = Date.now() + Math.random();
      setToasts((t) => [...t.slice(-3), { id, tone, message }]);
      window.setTimeout(() => dismiss(id), tone === "error" ? 7000 : 4500);
    },
    [dismiss],
  );

  const metaQuery = useApi<Meta>(ready ? `/api/meta` : null, [mode, version]);

  const activeFilterCount =
    (filters.start || filters.end ? 1 : 0) + filters.categories.length + filters.types.length + filters.merchants.length;

  const value = useMemo<AppState>(
    () => ({
      ready,
      mode,
      setMode,
      filters,
      setFilters,
      resetFilters,
      activeFilterCount,
      meta: metaQuery.data,
      metaError: metaQuery.error?.message ?? null,
      version,
      refresh,
      toasts,
      notify,
      dismiss,
    }),
    [ready, mode, setMode, filters, setFilters, resetFilters, activeFilterCount, metaQuery.data, metaQuery.error,
      version, refresh, toasts, notify, dismiss],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used inside <AppProvider>");
  return ctx;
}
