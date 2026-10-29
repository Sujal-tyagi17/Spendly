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
  is_covered: number | boolean;
  is_full_month: number | boolean;
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

export type Executive = {
  period: { start: string | null; end: string | null; filter_start: string | null; filter_end: string | null };
  expenditure_paise: number; income_paise: number; net_cash_flow_paise: number; refunds_paise: number; transaction_count: number;
  average_monthly_expenditure: { value_paise: number | null; months: number };
  month_over_month: { current_label: string; previous_label: string; current_paise: number; previous_paise: number;
    change_paise: number; change_pct: number | null; is_partial: boolean } | null;
  recurring: { estimated_monthly_paise: number; active_count: number; is_estimate: true };
  budget: { month: string; basis: string; budget_paise: number; actual_paise: number; utilisation_pct: number | null;
    is_full_month: boolean; status: string } | null;
};

export type ChangeStory = {
  available: boolean; headline: string | null; caveats: string[]; facts: Record<string, number | null>;
  points: { key: string; title: string; text: string; items: { name: string; change_paise: number; share_of_change_pct: number }[] }[];
  current_label?: string; previous_label?: string;
};

export type Overview = {
  executive: Executive;
  story: ChangeStory;
  weekend: WeekendRow[];
  anomaly_count: number;
  scorecard: { key: string; label: string; value_pct: number | null; numerator: number; denominator: number }[];
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
  story: ChangeStory;
  comparison: Comparison | null;
  headline: Insight | null;
  category_changes: (ChangeRow & { category: string })[];
  merchant_changes: (ChangeRow & { merchant: string })[];
  insights: Insight[];
  weekday: { weekday_name: string; transaction_count: number; expenditure_paise: number; avg_transaction_paise: number | null }[];
  largest: { id: number; transaction_date: string; merchant: string; category: string; amount_paise: number }[];
  anomalies: Anomaly[];
  anomaly_info: AnomalyInfo;
};

export type Anomaly = {
  id: number; transaction_date: string; merchant: string; category: string; amount_paise: number;
  method: string; basis: "merchant" | "category" | "rule"; reference_label: string; reference_count: number | null;
  median_paise: number | null; q1_paise: number | null; q3_paise: number | null; threshold_paise: number | null;
  mad_paise: number | null; robust_z: number | null; ratio_to_median: number | null; days_since_previous: number | null;
  deviation: "notable" | "large" | "extreme"; reason: string; review_status: string;
};

export type AnomalyInfo = {
  method: string; method_label: string; checked: number; insufficient_history: number;
  skipped_categories: Record<string, number>; checked_categories: string[]; checked_merchants: number;
  settings: { merchant_min_observations: number; min_observations: number; z_threshold: number; iqr_multiplier: number; min_ratio_to_median: number };
};

export type AnomalyEvalRun = {
  tp: number; fp: number; tn: number; fn: number; precision: number | null; recall: number | null; f1: number | null;
  not_checked: number; eligible: number; anomalies: number; by_kind: Record<string, { count: number; flagged: number }>;
};

export type AnomalyEvaluation = {
  seed: number; stability_seeds: number[]; tune_period: [string, string]; test_period: [string, string];
  dataset: { rows: number; eligible_expenses: number; anomalies: number; by_kind: Record<string, number> };
  results: { method: string; default_params: Record<string, number>; test_default: AnomalyEvalRun; tuned_params?: Record<string, number>;
    test_tuned?: AnomalyEvalRun; seeds: Record<"precision" | "recall" | "f1", { mean: number | null; sd: number | null; n: number }> }[];
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
  quality_report: ImportReport | null;
};

export type Severity = "error" | "warning" | "info";

export type ReportIssue = { code: string; label: string; severity: Severity; dimension: string; count: number; implication: string; unit: "rows" | "statement" };

export type ImportReport = {
  rows_extracted: number; rows_rejected: number; rows_accepted: number; rows_to_import: number;
  exact_duplicates_skipped: number; exact_duplicates_found: number; rows_complete: number;
  rejected_by_reason: Record<string, number>; field_issues: Record<string, number>;
  flags: { possible_duplicates: number; uncategorised: number; unknown_merchant: number; needs_review: number; balance_mismatch_rows: number; rows_without_balance: number };
  balance_check: { available: boolean; checked_pairs: number; mismatches: number; order: string | null; mismatch_rows: number[] };
  reconciliation: { available: boolean; opening_paise: number | null; closing_paise: number | null; credits_paise: number; debits_paise: number;
    computed_closing_paise: number | null; difference_paise: number | null; reconciled: boolean | null };
  dimensions: Record<string, number | null>;
  warnings: string[];
  issues: ReportIssue[];
};

export type QualityDimension = {
  key: string; label: string; numerator: number; denominator: number; value_pct: number | null;
  definition: string; note: string | null; higher_is_better: boolean;
};

export type Scorecard = {
  scope: { statement_id: number | null; statements: number; with_report: number; transactions: number };
  dimensions: QualityDimension[];
  issues: (Omit<ReportIssue, "count"> & { count: number; current_count: number | null; status_filter: string | null })[];
  categorisation_methods: Record<string, number>;
  rows_with_balance: number;
  trend: { statement_id: number; display_name: string; imported_at: string; rows_extracted: number; rows_rejected: number;
    exact_duplicates: number; possible_duplicates: number; balance_mismatches: number; uncategorised: number;
    completeness_pct: number | null; validity_pct: number | null }[];
  trend_available: boolean;
};

export type QualityResponse = {
  scorecard: Scorecard;
  counts: QualityCounts & { transactions: number; manual_corrections: number };
  statements: Statement[];
  all_statements: { id: number; display_name: string }[];
  issues: { statement_id: number; statement: string; page: number | null; row_number: number | null; reason: string; code: string; codes: string[]; severity: Severity; label: string }[];
  issue_breakdown: { code: string; label: string; count: number }[];
  issue_types: { code: string; label: string; severity: Severity; dimension: string; implication: string }[];
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
  report: ImportReport;
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

// ------------------------------------------------------------- budget planner

export type BudgetStatus = "over" | "at_limit" | "near" | "within" | "no_budget" | "no_data";

export type BudgetPace = {
  is_estimate: true;
  days_elapsed: number;
  days_remaining: number;
  projected_paise: number;
  expected_to_date_paise: number | null;
  pace: "faster" | "slower" | "on_pace" | null;
  pace_pct?: number;
};

export type BudgetRow = {
  category: string;
  budget_id: number | null;
  budget_paise: number | null;
  actual_paise: number;
  transaction_count: number;
  remaining_paise: number | null;
  variance_paise: number | null;
  utilisation_pct: number | null;
  variance_pct: number | null;
  status: BudgetStatus;
  pace: BudgetPace | null;
};

export type BudgetOverall = {
  overall_budget_id: number | null;
  overall_budget_paise: number | null;
  category_budgets_paise: number;
  budgeted_category_count: number;
  expenditure_paise: number;
  refunds_paise: number;
  net_expenditure_paise: number;
  unbudgeted_paise: number;
  remaining_paise: number | null;
  variance_paise: number | null;
  utilisation_pct: number | null;
  variance_pct: number | null;
  status: BudgetStatus;
  pace: BudgetPace | null;
};

export type BudgetInsight = {
  key: string;
  kind: "observed" | "estimate";
  tone: "neutral" | "up" | "down" | "warning";
  title: string;
  text: string;
  link: InsightLink | null;
};

export type BudgetCoverage = {
  is_covered: boolean;
  is_full: boolean;
  covered_from: string | null;
  covered_to: string | null;
  days_covered: number;
  days_in_month: number;
};

export type BudgetReport = {
  month: string;
  coverage: BudgetCoverage;
  rows: BudgetRow[];
  overall: BudgetOverall;
  previous_month: string;
  previous_has_budgets: boolean;
  insights: BudgetInsight[];
  history: { month: string; budget_paise: number | null; budget_basis: string | null; actual_paise: number; is_full: boolean }[];
  categories: string[];
  settings: { near_threshold_pct: number; pace_min_days: number; pace_tolerance_pct: number; repeat_window_months: number; repeat_min_months: number };
};

export type BudgetMonths = { months: { month: string; has_data: boolean; has_budgets: boolean }[]; default: string };

export type BudgetDrivers = {
  month: string;
  category: string;
  merchants: { merchant: string; transaction_count: number; expenditure_paise: number; share_pct: number }[];
  change: { merchant: string; current_paise: number; previous_paise: number; change_paise: number; change_pct: number | null }[];
  largest: { id: number; transaction_date: string; merchant?: string; normalized_merchant?: string; amount_paise: number }[];
};
