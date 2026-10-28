"use client";

/**
 * Tiny API client. The browser only ever talks to same-origin `/api/*`
 * (proxied to FastAPI by next.config.ts). No financial calculation happens
 * here — every number shown in the app comes from the backend.
 */

import { useCallback, useEffect, useRef, useState } from "react";

export type Mode = "demo" | "user";

export type Filters = {
  start: string | null;
  end: string | null;
  categories: string[];
  types: string[];
  merchants: string[];
};

export const EMPTY_FILTERS: Filters = { start: null, end: null, categories: [], types: [], merchants: [] };

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

let currentMode: Mode = "demo";
let sessionId: string | null = null;

export function setApiMode(mode: Mode) {
  currentMode = mode;
}

function session(): string {
  if (sessionId) return sessionId;
  try {
    sessionId = window.sessionStorage.getItem("spendly.session");
    if (!sessionId) {
      sessionId = crypto.randomUUID().replace(/-/g, "");
      window.sessionStorage.setItem("spendly.session", sessionId);
    }
  } catch {
    sessionId = crypto.randomUUID().replace(/-/g, "");
  }
  return sessionId;
}

export function headers(extra: Record<string, string> = {}): Record<string, string> {
  return { "X-Spendly-Mode": currentMode, "X-Spendly-Session": session(), ...extra };
}

export function filtersToQuery(filters: Partial<Filters> & { statuses?: string[]; search?: string }, extra: Record<string, string | number | undefined> = {}): string {
  const q = new URLSearchParams();
  if (filters.start) q.set("start", filters.start);
  if (filters.end) q.set("end", filters.end);
  filters.categories?.forEach((c) => q.append("categories", c));
  filters.types?.forEach((t) => q.append("types", t));
  filters.merchants?.forEach((m) => q.append("merchants", m));
  filters.statuses?.forEach((s) => q.append("statuses", s));
  if (filters.search) q.set("search", filters.search);
  Object.entries(extra).forEach(([k, v]) => v !== undefined && v !== "" && q.set(k, String(v)));
  const s = q.toString();
  return s ? `?${s}` : "";
}

async function parse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = `Request failed (${res.status}).`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") message = body.detail;
      else if (Array.isArray(body?.detail)) message = "Some of the values sent were not valid.";
    } catch {
      if (res.status >= 500) message = "The Spendly API isn't reachable. Is the backend running?";
    }
    throw new ApiError(res.status, message);
  }
  return res.json() as Promise<T>;
}

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { headers: headers(), signal, cache: "no-store" });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, "Couldn't reach the Spendly API. Check that the backend is running.");
  }
  return parse<T>(res);
}

export async function apiSend<T>(path: string, method: "POST" | "PATCH" | "DELETE", body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      headers: headers({ "Content-Type": "application/json" }),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Couldn't reach the Spendly API. Check that the backend is running.");
  }
  return parse<T>(res);
}

export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { method: "POST", headers: headers(), body: form });
  } catch {
    throw new ApiError(0, "Couldn't reach the Spendly API. Check that the backend is running.");
  }
  return parse<T>(res);
}

export async function downloadFile(path: string, filename: string) {
  const res = await fetch(path, { headers: headers() });
  if (!res.ok) throw new ApiError(res.status, "Export failed.");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/**
 * Fetch hook that keeps the previous data while refetching, so the layout
 * doesn't jump when filters change.
 */
export function useApi<T>(path: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState<boolean>(!!path);
  const [tick, setTick] = useState(0);
  const first = useRef(true);

  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loading flag for an external fetch
    setLoading(true);
    apiGet<T>(path, controller.signal)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => {
        if ((e as Error).name === "AbortError") return;
        setError(e instanceof ApiError ? e : new ApiError(0, "Something went wrong."));
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
          first.current = false;
        }
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, tick, ...deps]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, initialLoading: loading && data === null, reload };
}
