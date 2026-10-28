"use client";

import { useRouter } from "next/navigation";
import { useCallback } from "react";
import { EMPTY_FILTERS, filtersToQuery, useApi } from "./api";
import { useApp } from "./store";
import type { InsightLink } from "./types";

/** GET an endpoint with the global filters applied; refetches on mode/filter/data changes. */
export function useFiltered<T>(path: string, extra: Record<string, string | number | undefined> = {}, useFilters = true) {
  const { ready, filters, mode, version } = useApp();
  const url = ready ? `${path}${filtersToQuery(useFilters ? filters : {}, extra)}` : null;
  return useApi<T>(url, [mode, version]);
}

/** Jump to the transaction explorer showing exactly the rows behind an insight. */
export function useOpenTransactions() {
  const { setFilters } = useApp();
  const router = useRouter();
  return useCallback(
    (link: InsightLink) => {
      setFilters({
        ...EMPTY_FILTERS,
        start: link.start ?? null,
        end: link.end ?? null,
        categories: link.categories ?? [],
        merchants: link.merchants ?? [],
        types: link.types ?? [],
      });
      const status = link.statuses?.[0];
      router.push(`/app/transactions${status ? `?status=${encodeURIComponent(status)}` : ""}`);
    },
    [router, setFilters],
  );
}
