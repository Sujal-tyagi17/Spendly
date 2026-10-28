"use client";

import { AnimatePresence, motion } from "motion/react";
import { Trash2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ApiError, apiGet, apiSend } from "@/lib/api";
import { fmtDate, inr, TYPE_LABELS } from "@/lib/format";
import { useApp } from "@/lib/store";
import type { Txn } from "@/lib/types";
import { StatusBadge } from "../ui/badges";
import { Button } from "../ui/button";

const selectCls = "mt-1.5 h-10 w-full rounded-xl border border-line bg-ink-2 px-3 text-[0.86rem] text-fg";

/**
 * Edits one transaction through the API. A merchant-wide category change shows
 * the exact number of affected rows and sends it back as `expected_count`; the
 * backend refuses the change if the number no longer matches.
 */
export function EditTransactionDialog({ txn, onClose }: { txn: Txn | null; onClose: () => void }) {
  const { meta, refresh, notify } = useApp();
  const [category, setCategory] = useState("");
  const [type, setType] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [applyAll, setApplyAll] = useState(false);
  const [scope, setScope] = useState<{ count: number; merchant: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!txn) return;
    /* eslint-disable react-hooks/set-state-in-effect -- reset the form for the newly opened row */
    setCategory(txn.category);
    setType(txn.type);
    setReviewed(false);
    setApplyAll(false);
    setConfirmDelete(false);
    setError(null);
    setScope(null);
    /* eslint-enable react-hooks/set-state-in-effect */
    apiGet<{ count: number; merchant: string }>(`/api/transactions/${txn.id}/merchant-scope`).then(setScope).catch(() => setScope(null));
    const t = window.setTimeout(() => panel.current?.querySelector<HTMLElement>("select")?.focus(), 40);
    const key = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", key);
    return () => { window.clearTimeout(t); window.removeEventListener("keydown", key); };
  }, [txn, onClose]);

  if (!txn) return <AnimatePresence />;

  const changed = category !== txn.category || type !== txn.type || reviewed;
  const typeOptions = (meta?.transaction_types ?? []).map((t) => t.key)
    .filter((k) => (txn.direction === "debit" ? ["expense", "transfer", "cc_repayment"] : ["income", "refund", "transfer", "other"]).includes(k));

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {};
      if (category !== txn.category) body.category = category;
      if (type !== txn.type) body.transaction_type = type;
      if (reviewed) body.mark_reviewed = true;
      if (applyAll && body.category && scope) {
        body.apply_to_merchant = true;
        body.expected_count = scope.count;
      }
      const res = await apiSend<{ updated: number }>(`/api/transactions/${txn.id}`, "PATCH", body);
      notify(res.updated > 1 ? `Updated ${res.updated} transactions from ${txn.merchant}.` : "Transaction updated.");
      refresh();
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't save the change.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await apiSend(`/api/transactions/${txn.id}`, "DELETE");
      notify("Transaction deleted.");
      refresh();
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't delete the transaction.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AnimatePresence>
      <motion.div className="fixed inset-0 z-[80] flex items-end justify-center p-0 sm:items-center sm:p-4"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
        <div className="absolute inset-0 bg-black/70" onClick={onClose} aria-hidden="true" />
        <motion.div ref={panel} role="dialog" aria-modal="true" aria-labelledby="edit-title"
          initial={{ y: 24, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          className="relative max-h-[92dvh] w-full overflow-y-auto rounded-t-2xl border border-line-2 bg-elevated p-5 sm:max-w-lg sm:rounded-2xl sm:p-6">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h2 id="edit-title" className="truncate text-lg font-semibold tracking-tight">{txn.merchant}</h2>
              <p className="mt-0.5 text-[0.8rem] text-muted">
                {fmtDate(txn.date)} · <span className={`tabular ${txn.direction === "credit" ? "text-pos" : "text-fg"}`}>
                  {inr(txn.direction === "credit" ? txn.amount_paise : -txn.amount_paise, { sign: true, decimals: true })}</span>
              </p>
            </div>
            <button type="button" onClick={onClose} aria-label="Close" className="rounded-lg p-1.5 text-faint hover:text-fg"><X className="h-5 w-5" aria-hidden="true" /></button>
          </div>

          <p className="mt-3 rounded-lg border border-line bg-ink-2 px-3 py-2 font-mono text-[0.72rem] break-all text-muted">{txn.description}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-[0.75rem] text-muted">
            <StatusBadge status={txn.review_status} duplicate={txn.is_possible_duplicate} method={txn.method} />
            {txn.review_reason ? <span>{txn.review_reason}</span> : null}
          </div>

          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <label className="text-[0.75rem] font-medium text-muted">Category
              <select value={category} onChange={(e) => setCategory(e.target.value)} className={selectCls}>
                {(meta?.categories ?? []).map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
            <label className="text-[0.75rem] font-medium text-muted">Type
              <select value={type} onChange={(e) => setType(e.target.value)} className={selectCls}>
                {typeOptions.map((k) => <option key={k} value={k}>{TYPE_LABELS[k]}</option>)}
              </select>
            </label>
          </div>
          <p className="mt-2 text-[0.72rem] leading-relaxed text-faint">
            Changing only the category updates the type to match (e.g. &ldquo;Income&rdquo; on a credit makes it income).
          </p>

          {category !== txn.category && scope && scope.count > 1 ? (
            <label className="mt-4 flex items-start gap-3 rounded-xl border border-warn/25 bg-warn/[0.05] p-3 text-[0.84rem]">
              <input type="checkbox" checked={applyAll} onChange={(e) => setApplyAll(e.target.checked)} className="mt-0.5 h-4 w-4 accent-[#c6ff5e]" />
              <span>
                Also set <b>{category}</b> on all <b>{scope.count}</b> {txn.direction === "debit" ? "payments to" : "credits from"} {scope.merchant}.
                <span className="mt-0.5 block text-[0.75rem] text-muted">This changes {scope.count} transactions. Nothing else is touched.</span>
              </span>
            </label>
          ) : null}

          {txn.review_status === "needs_review" || txn.is_possible_duplicate ? (
            <label className="mt-4 flex items-center gap-3 text-[0.86rem]">
              <input type="checkbox" checked={reviewed} onChange={(e) => setReviewed(e.target.checked)} className="h-4 w-4 accent-[#c6ff5e]" />
              {txn.is_possible_duplicate ? "This is a real payment, not a duplicate" : "Mark as reviewed"}
            </label>
          ) : null}

          {error ? <p role="alert" className="mt-4 text-[0.82rem] text-[#ff9b8f]">{error}</p> : null}

          <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between">
            {txn.is_possible_duplicate ? (
              confirmDelete ? (
                <Button variant="danger" onClick={remove} loading={busy}><Trash2 className="h-4 w-4" aria-hidden="true" />Confirm delete</Button>
              ) : (
                <Button variant="ghost" onClick={() => setConfirmDelete(true)}><Trash2 className="h-4 w-4" aria-hidden="true" />Delete duplicate</Button>
              )
            ) : <span />}
            <div className="flex flex-col-reverse gap-2 sm:flex-row">
              <Button onClick={onClose}>Cancel</Button>
              <Button variant="primary" onClick={save} loading={busy} disabled={!changed}>
                {applyAll && scope ? `Save ${scope.count} changes` : "Save"}
              </Button>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
