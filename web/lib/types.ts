/** Shapes returned by the FastAPI backend (api/main.py). Amounts are integer paise. */

export type Totals = {
  transaction_count: number;
  first_date: string | null;
  last_date: string | null;
  gross_debits_paise: number;
  total_credits_paise: number;
  expenditure_paise: number;
  refunds_paise: number;
  income_paise: number;
  transfers_paise: number;
  cc_repayments_paise: number;
  net_cash_flow_paise: number;
  uncategorized_count: number;
  uncategorized_debits_paise: number;
  needs_review_count: number;
  possible_duplicate_count: number;
};

export type MonthSummary = {
  month_start: string;
  expenditure_paise: number;
  refunds_paise: number;
  net_expenditure_paise: number;
  income_paise: number;
  net_cash_flow_paise: number;
  transaction_count: number;
  prev_expenditure_paise: number | null;
  mom_change_pct: number | null;
};

export type CategoryRow = {
  category: string;
  transaction_count: number;
  expenditure_paise: number;
  avg_transaction_paise: number;
  share_pct: number | null;
  spend_rank: number;
};

export type MerchantRow = {
  merchant: string;
  category: string;
  transaction_count: number;
  expenditure_paise: number;
  share_pct: number | null;
};

export type Txn = {
  id: number;
  date: string;
  merchant: string;
  description: string;
  amount_paise: number;
  direction: "debit" | "credit";
  type: string;
  category: string;
  method: string;
  review_status: string;
  review_reason: string | null;
  is_possible_duplicate: boolean;
  balance_paise: number | null;
};

export type Comparison = {
  current: { start: string; end: string; label: string };
  previous: { start: string; end: string; label: string };
  is_partial: boolean;
  current_paise: number;
  previous_paise: number;
  change_paise: number;
  change_pct: number | null;
};

export type InsightLink = {
  start?: string;
  end?: string;
  categories?: string[];
  merchants?: string[];
  types?: string[];
  statuses?: string[];
};

export type Insight = {
  key: string;
  title: string;
  text: string;
  tone: "neutral" | "up" | "down" | "warning" | "good";
  period: string | null;
  value_paise: number | null;
  value_pct: number | null;
  subject: string | null;
  link: InsightLink | null;
};

export type QualityCounts = {
  rows_extracted: number;
  rows_invalid: number;
  duplicates_skipped: number;
  balance_checked_pairs: number;
  balance_mismatches: number;
  possible_duplicates: number;
  uncategorized: number;
  needs_review: number;
};

export type Overview = {
  totals: Totals;
  monthly: MonthSummary[];
  categories: CategoryRow[];
  top_merchants: MerchantRow[];
  recent: Txn[];
  comparison: Comparison | null;
  insights: Insight[];
  quality: QualityCounts;
  coverage: { start: string | null; end: string | null };
};

export type ChangeRow = { current_paise: number; previous_paise: number; change_paise: number; change_pct: number | null };

export type InsightsResponse = {
  comparison: Comparison | null;
  headline: Insight | null;
  category_changes: (ChangeRow & { category: string })[];
  merchant_changes: (ChangeRow & { merchant: string })[];
  insights: Insight[];
  weekday: { weekday_name: string; transaction_count: number; expenditure_paise: number; avg_transaction_paise: number | null }[];
  largest: { id: number; transaction_date: string; merchant: string; category: string; amount_paise: number }[];
  anomalies: {
    id: number; transaction_date: string; merchant: string; category: string; amount_paise: number; basis: string;
    median_paise: number; threshold_paise: number; ratio_to_median: number; reason: string; review_status: string;
  }[];
  anomaly_info: { checked_categories: string[]; skipped_categories: Record<string, number>; checked_merchants: number };
};

export type Recurring = {
  merchant: string;
  category: string;
  status: "confirmed" | "high_confidence" | "possible" | "rejected";
  kind: string;
  schedule: string;
  occurrences: number;
  median_amount_paise: number;
  min_amount_paise: number;
  max_amount_paise: number;
  est_monthly_paise: number;
  est_annual_paise: number;
  first_payment: string;
  last_payment: string;
  next_expected: string;
  possibly_stopped: boolean;
  rationale: string;
};

export type RecurringResponse = {
  candidates: Recurring[];
  monthly_total_paise: number;
  annual_total_paise: number;
  settings: { min_occurrences: number; tolerance_days: Record<string, number>; high_amount_tolerance: number; possible_amount_tolerance: number };
};

export type Statement = {
  id: number; display_name: string; parser_name: string; statement_period_start: string | null;
  statement_period_end: string | null; rows_extracted: number; rows_imported: number; rows_invalid: number;
  rows_skipped_duplicates: number; balance_checked_pairs: number; balance_mismatches: number; warnings: string[];
  created_at: string;
};

export type QualityResponse = {
  counts: QualityCounts & { rows_without_balance: number; rows_unknown_merchant: number; transactions: number; manual_corrections: number };
  statements: Statement[];
  issues: { statement: string; page: number | null; row_number: number | null; reason: string }[];
  issue_breakdown: { kind: string; count: number }[];
  uncategorized: { merchant: string; direction: string; transaction_count: number; total_paise: number; last_seen: string }[];
  corrections: { corrected_at: string; merchant: string; field: string; old_value: string; new_value: string }[];
};

export type PreviewRow = {
  row_number: number; page: number | null; date: string; description: string; merchant: string; amount_paise: number;
  direction: "debit" | "credit"; type: string; category: string; method: string; duplicate_status: string;
  review_reason: string | null;
};

export type ImportPreview = {
  token: string;
  parser: { name: string; label: string };
  period: { start: string | null; end: string | null };
  counts: { extracted: number; valid: number; invalid: number; exact_duplicates: number; possible_duplicates: number; uncategorized: number; to_import: number };
  balance_check: { checked_pairs: number; mismatches: number };
  warnings: string[];
  already_imported: boolean;
  rows: PreviewRow[];
  invalid_rows: { row_number: number; page: number | null; reason: string }[];
  ai: { enabled: boolean; message: string; payload: string[]; uncategorized_merchants: number };
};

export type CommitResult = { statement_id: number; imported: number; skipped_duplicates: number; invalid: number; flagged_for_review: number };

export type AnalysisMonth = MonthSummary & {
  is_covered: number;
  is_full_month: number;
  prev_status: "none" | "not_covered" | "zero" | "value";
  expenditure_change_paise: number | null;
  cumulative_net_cash_flow_paise: number;
  transfers_paise: number;
  cc_repayments_paise: number;
};

export type CategoryMonth = {
  month_start: string; category: string; expenditure_paise: number; transaction_count: number;
  prev_expenditure_paise: number | null; change_paise: number | null; change_pct: number | null;
  share_of_month_pct: number | null; share_of_change_pct: number | null; rank_in_month: number;
};

export type MerchantStat = {
  merchant: string; category: string; transaction_count: number; expenditure_paise: number;
  avg_transaction_paise: number; median_transaction_paise: number; first_seen: string; last_seen: string;
  active_months: number; share_pct: number; cumulative_share_pct: number; spend_rank: number; frequency_rank: number;
};

export type WeekendRow = {
  scope: string; weekday_paise: number; weekend_paise: number; weekday_txns: number; weekend_txns: number;
  weekday_days: number; weekend_days: number; weekday_avg_txn_paise: number | null; weekend_avg_txn_paise: number | null;
  weekday_per_day_paise: number | null; weekend_per_day_paise: number | null; weekend_share_pct: number | null;
};

export type AnalysisResponse = {
  range: { start: string | null; end: string | null };
  totals: Totals;
  monthly: AnalysisMonth[];
  categories: CategoryRow[];
  category_monthly: CategoryMonth[];
  merchants: MerchantStat[];
  merchant_count: number;
  concentration: {
    merchant_count: number; expenditure_paise: number; top_1_share_pct: number | null; top_5_share_pct: number | null;
    top_10_share_pct: number | null; hhi: number | null; hhi_level: "low" | "moderate" | "high" | null;
    top_merchant: string | null; category_count: number; top_category: string | null; top_category_share_pct: number | null;
  };
  weekday: { weekday_name: string; transaction_count: number; expenditure_paise: number; avg_transaction_paise: number | null }[];
  weekend: WeekendRow[];
  recurring: {
    merchants: string[]; estimated_monthly_paise: number; estimated_annual_paise: number; actual_recurring_paise: number;
    total_expenditure_paise: number; share_of_expenditure_pct: number | null;
    monthly: { month_start: string; recurring_paise: number; expenditure_paise: number; share_pct: number | null }[];
  };
  definitions: Record<string, string>;
};
