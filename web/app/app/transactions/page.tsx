"use client";

import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Download, Pencil, Search } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { EditTransactionDialog } from "@/components/app/edit-transaction";
import { NoDataState } from "@/components/app/no-data";
import { CategoryBadge, StatusBadge, TypeBadge } from "@/components/ui/badges";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { downloadFile, EMPTY_FILTERS, filtersToQuery, useApi } from "@/lib/api";
import { fmtDate, inr } from "@/lib/format";
import { useApp } from "@/lib/store";
import type { Txn } from "@/lib/types";

type Page = { rows: Txn[]; total: number; page: number; page_size: number; summary: { debits_paise: number; credits_paise: number; needs_review: number } };
type SortKey = "date" | "merchant" | "category" | "type" | "amount";

const STATUS_TABS = [
  { key: "", label: "All" },
  { key: "needs_review", label: "Needs review" },
  { key: "possible_duplicate", label: "Possible duplicates" },
  { key: "uncategorized", label: "Uncategorized" },
] as const;
// Reached only through deep links from the Data Quality scorecard; shown as a tab while active.
const LINK_ONLY_TABS = [
  { key: "balance_mismatch", label: "Balance mismatches" },
  { key: "unknown_merchant", label: "Unrecognised merchants" },
] as const;

function SortHeader({ k, label, sort, order, onToggle, className = "" }: {
  k: SortKey; label: string; sort: SortKey; order: "asc" | "desc"; onToggle: (k: SortKey) => void; className?: string;
}) {
  return (
    <th scope="col" aria-sort={sort === k ? (order === "asc" ? "ascending" : "descending") : "none"} className={`px-3 py-3 font-medium ${className}`}>
      <button type="button" onClick={() => onToggle(k)} className={`inline-flex items-center gap-1 rounded transition-colors hover:text-fg ${sort === k ? "text-fg" : ""}`}>
        {label}
        {sort === k ? (order === "asc" ? <ArrowUp className="h-3 w-3" aria-hidden="true" /> : <ArrowDown className="h-3 w-3" aria-hidden="true" />) : null}
      </button>
    </th>
  );
}

function Amount({ t }: { t: Txn }) {
  const signed = t.direction === "credit" ? t.amount_paise : -t.amount_paise;
  return (
    <span className={`tabular ${t.direction === "credit" ? "text-pos" : "text-fg"}`}>
      {inr(signed, { sign: true, decimals: true })}
      <span className="sr-only">{t.direction === "credit" ? " money in" : " money out"}</span>
    </span>
  );
}

export default function TransactionsPage() {
  const { ready, filters, setFilters, mode, version, meta, notify } = useApp();
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<string>("");
  const [sort, setSort] = useState<SortKey>("date");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [editing, setEditing] = useState<Txn | null>(null);
  const [exporting, setExporting] = useState(false);

  // Deep links from insights / data quality: /app/transactions?status=uncategorized
  useEffect(() => {
    const s = new URLSearchParams(window.location.search).get("status");
    // eslint-disable-next-line react-hooks/set-state-in-effect -- read deep link once on mount
    if (s && [...STATUS_TABS, ...LINK_ONLY_TABS].some((t) => t.key === s)) setStatus(s);
  }, []);

  useEffect(() => {
    const t = window.setTimeout(() => { setSearch(searchInput.trim()); setPage(1); }, 300);
    return () => window.clearTimeout(t);
  }, [searchInput]);

  // eslint-disable-next-line react-hooks/set-state-in-effect -- new filters → back to page 1
  useEffect(() => { setPage(1); }, [filters, status, pageSize]);

  const query = filtersToQuery({ ...filters, statuses: status ? [status] : [], search }, { sort, order, page, page_size: pageSize });
  const { data, error, loading, initialLoading, reload } = useApi<Page>(ready ? `/api/transactions${query}` : null, [mode, version]);
  const close = useCallback(() => setEditing(null), []);

  const toggleSort = (key: SortKey) => {
    if (sort === key) setOrder(order === "desc" ? "asc" : "desc");
    else { setSort(key); setOrder(key === "merchant" || key === "category" || key === "type" ? "asc" : "desc"); }
    setPage(1);
  };

  const exportCsv = async () => {
    setExporting(true);
    try {
      await downloadFile(`/api/transactions/export.csv${filtersToQuery({ ...filters, statuses: status ? [status] : [], search })}`, "spendly_transactions.csv");
      notify("Exported the transactions matching your current filters.");
    } catch {
      notify("Export failed. Please try again.", "error");
    } finally {
      setExporting(false);
    }
  };

  if (meta && meta.counts.transactions === 0) return <NoDataState />;

  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  return (
    <div className="space-y-4">
      {/* ---------- toolbar */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <label className="flex h-10 w-full items-center gap-2 rounded-xl border border-line bg-ink-2 px-3 transition-colors focus-within:border-line-2 lg:max-w-sm">
          <Search className="h-4 w-4 text-faint" aria-hidden="true" />
          <input value={searchInput} onChange={(e) => setSearchInput(e.target.value)} placeholder="Search merchant or description"
            aria-label="Search transactions" className="h-full w-full bg-transparent text-[0.86rem] text-fg outline-none placeholder:text-faint" />
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <div role="tablist" aria-label="Review status" className="flex flex-wrap gap-1 rounded-xl border border-line bg-ink-2 p-1">
            {[...STATUS_TABS, ...LINK_ONLY_TABS.filter((t) => t.key === status)].map((t) => (
              <button key={t.key} role="tab" type="button" aria-selected={status === t.key} onClick={() => setStatus(t.key)}
                className={`rounded-lg px-2.5 py-1.5 text-[0.76rem] font-medium transition-colors ${status === t.key ? "bg-white/[0.08] text-fg" : "text-muted hover:text-fg"}`}>
                {t.label}
              </button>
            ))}
          </div>
          <Button onClick={exportCsv} loading={exporting} disabled={!data?.total}>
            <Download className="h-4 w-4" aria-hidden="true" />Export CSV
          </Button>
        </div>
      </div>

      {data ? (
        <p className="text-[0.8rem] text-muted" aria-live="polite">
          <span className="tabular text-fg">{data.total.toLocaleString("en-IN")}</span> transactions · money out{" "}
          <span className="tabular text-fg">{inr(data.summary.debits_paise)}</span> · money in{" "}
          <span className="tabular text-pos">{inr(data.summary.credits_paise)}</span>
          {data.summary.needs_review ? <> · <span className="text-warn">{data.summary.needs_review} need review</span></> : null}
          {loading ? <span className="ml-2 text-faint">Updating…</span> : null}
        </p>
      ) : null}

      {error && !data ? <ErrorState message={error.message} onRetry={reload} /> : null}
      {initialLoading ? <LoadingState label="Loading transactions" rows={8} /> : null}

      {data && data.total === 0 ? (
        <EmptyState title="No transactions match"
          action={<Button onClick={() => { setSearchInput(""); setStatus(""); setFilters(EMPTY_FILTERS); }}>Clear search & filters</Button>}>
          {status ? "Nothing in this review list right now — that's good news." : "Try a different search, or widen the date range."}
        </EmptyState>
      ) : null}

      {data && data.total > 0 ? (
        <div className={`transition-opacity duration-200 ${loading ? "opacity-60" : ""}`}>
          {/* desktop table */}
          <div className="hidden overflow-x-auto rounded-2xl border border-line bg-card md:block">
            <table className="w-full table-fixed text-left text-[0.84rem]">
              <caption className="sr-only">Transactions, sorted by {sort} {order === "asc" ? "ascending" : "descending"}</caption>
              <colgroup>
                <col className="w-[7.5rem]" /><col /><col className="w-[10.5rem]" /><col className="w-[8.5rem]" />
                <col className="w-[9.5rem]" /><col className="w-[10.5rem]" /><col className="w-[3.5rem]" />
              </colgroup>
              <thead className="border-b border-line text-[0.72rem] text-muted">
                <tr>
                  <SortHeader sort={sort} order={order} onToggle={toggleSort} k="date" label="Date" />
                  <SortHeader sort={sort} order={order} onToggle={toggleSort} k="merchant" label="Merchant" />
                  <SortHeader sort={sort} order={order} onToggle={toggleSort} k="category" label="Category" />
                  <SortHeader sort={sort} order={order} onToggle={toggleSort} k="type" label="Type" />
                  <SortHeader sort={sort} order={order} onToggle={toggleSort} k="amount" label="Amount" className="text-right [&>button]:ml-auto [&>button]:flex" />
                  <th scope="col" className="px-3 py-3 font-medium">Status</th>
                  <th scope="col" className="px-3 py-3"><span className="sr-only">Edit</span></th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((t) => (
                  <tr key={t.id} className={`border-b border-line/60 transition-colors last:border-0 hover:bg-white/[0.025] ${t.is_possible_duplicate ? "bg-warn/[0.03]" : ""}`}>
                    <td className="tabular px-3 py-3 whitespace-nowrap text-muted">{fmtDate(t.date)}</td>
                    <td className="px-3 py-3">
                      <p className="truncate text-fg">{t.merchant}</p>
                      <p className="truncate font-mono text-[0.68rem] text-faint" title={t.description}>{t.description}</p>
                    </td>
                    <td className="px-3 py-3"><CategoryBadge category={t.category} /></td>
                    <td className="px-3 py-3"><TypeBadge type={t.type} /></td>
                    <td className="px-3 py-3 text-right whitespace-nowrap"><Amount t={t} /></td>
                    <td className="px-3 py-3"><StatusBadge status={t.review_status} duplicate={t.is_possible_duplicate} method={t.method} /></td>
                    <td className="px-2 py-3 text-right">
                      <button type="button" onClick={() => setEditing(t)} aria-label={`Edit ${t.merchant} on ${fmtDate(t.date)}`}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-faint transition-colors hover:bg-white/[0.06] hover:text-fg">
                        <Pencil className="h-4 w-4" aria-hidden="true" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* mobile list */}
          <ul className="space-y-2 md:hidden">
            {data.rows.map((t) => (
              <li key={t.id}>
                <button type="button" onClick={() => setEditing(t)} className="w-full rounded-2xl border border-line bg-card p-4 text-left">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-[0.92rem] font-medium text-fg">{t.merchant}</p>
                      <p className="mt-0.5 text-[0.72rem] text-faint">{fmtDate(t.date)}</p>
                    </div>
                    <Amount t={t} />
                  </div>
                  <div className="mt-2.5 flex flex-wrap gap-1.5">
                    <CategoryBadge category={t.category} /><TypeBadge type={t.type} />
                    {t.review_status !== "ok" || t.is_possible_duplicate ? <StatusBadge status={t.review_status} duplicate={t.is_possible_duplicate} method={t.method} /> : null}
                  </div>
                </button>
              </li>
            ))}
          </ul>

          {/* pagination */}
          <nav aria-label="Pagination" className="mt-4 flex flex-wrap items-center justify-between gap-3 text-[0.8rem] text-muted">
            <label className="flex items-center gap-2">Rows per page
              <select value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))}
                className="h-9 rounded-lg border border-line bg-ink-2 px-2 text-fg">
                {[25, 50, 100, 250].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
            <div className="flex items-center gap-2">
              <span className="tabular">Page {page} of {pages}</span>
              <Button size="sm" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1} aria-label="Previous page">
                <ChevronLeft className="h-4 w-4" aria-hidden="true" />
              </Button>
              <Button size="sm" onClick={() => setPage((p) => Math.min(pages, p + 1))} disabled={page >= pages} aria-label="Next page">
                <ChevronRight className="h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
          </nav>
        </div>
      ) : null}

      <EditTransactionDialog txn={editing} onClose={close} />
    </div>
  );
}
