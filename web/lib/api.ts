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

function storedSession(): string | null {
  if (sessionId) return sessionId;
  try {
    sessionId = window.sessionStorage.getItem("spendly.session");
  } catch {}
  return sessionId;
}

let renewing: Promise<void> | null = null;

/**
 * Public deployments need a server-issued session token (POST /api/session). It lives in
 * sessionStorage for this tab only and is sent as a header, never in a URL. Local
 * deployments don't use sessions and return none.
 */
function renewSession(): Promise<void> {
  renewing ??= (async () => {
    try {
      const res = await fetch("/api/session", { method: "POST", cache: "no-store" });
      const body = res.ok ? await res.json() : null;
      sessionId = body?.session ?? null;
      try {
        if (sessionId) window.sessionStorage.setItem("spendly.session", sessionId);
        else window.sessionStorage.removeItem("spendly.session");
      } catch {}
    } finally {
      renewing = null;
    }
  })();
  return renewing;
}

export function headers(extra: Record<string, string> = {}): Record<string, string> {
  const s = storedSession();
  return { "X-Spendly-Mode": currentMode, ...(s ? { "X-Spendly-Session": s } : {}), ...extra };
}

/** fetch with the Spendly headers; starts (or restarts) a session once if the API asks for one. */
async function send(path: string, init: RequestInit & { extraHeaders?: Record<string, string> } = {}): Promise<Response> {
  const { extraHeaders, ...rest } = init;
  const go = () => fetch(path, { ...rest, headers: headers(extraHeaders) });
  let res = await go();
  if (res.status === 401) {
    const body = await res.clone().json().catch(() => null);
    if (body?.code === "session_required") {
      await renewSession();
      res = await go();
    }
  }
  return res;
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
    res = await send(path, { signal, cache: "no-store" });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, "Couldn't reach the Spendly API. Check that the backend is running.");
  }
  return parse<T>(res);
}

export async function apiSend<T>(path: string, method: "POST" | "PATCH" | "DELETE", body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await send(path, {
      method,
      extraHeaders: { "Content-Type": "application/json" },
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
    res = await send(path, { method: "POST", body: form });
  } catch {
    throw new ApiError(0, "Couldn't reach the Spendly API. Check that the backend is running.");
  }
  return parse<T>(res);
}

export async function downloadFile(path: string, filename: string) {
  const res = await send(path);
  if (!res.ok) throw new ApiError(res.status, res.status === 429 ? "Too many downloads. Please wait a moment." : "Export failed.");
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
