import { apiClient } from "./client";

export interface AccountingPeriod {
  id: string;
  company_id: string;
  name: string;
  start_date: string;
  end_date: string;
  status: "open" | "closing" | "closed" | "reopened";
  version: number;
}

export async function getAccountingPeriods(): Promise<AccountingPeriod[]> {
  return (await apiClient.get<AccountingPeriod[]>("/api/v1/accounting/periods"))
    .data;
}

export type ReportFamily =
  | "trial_balance"
  | "profit_and_loss"
  | "balance_sheet"
  | "general_ledger"
  | "ar_aging"
  | "ap_aging"
  | "cash_flow"
  | "job_costing";

export interface ReportLineDifference {
  identity: string;
  label: string;
  acp_classification: string | null;
  qbo_classification: string | null;
  acp_amount: string | null;
  qbo_amount: string | null;
  difference: string | null;
  acp_debit: string | null;
  acp_credit: string | null;
  qbo_debit: string | null;
  qbo_credit: string | null;
  disposition: string;
}

export interface ReportComparison {
  family: ReportFamily;
  acp_available: boolean;
  qbo_available: boolean;
  state: "COMPARABLE" | "NOT_COMPARABLE" | "UNAVAILABLE";
  non_comparable_reasons: string[];
  start_date: string | null;
  end_date: string | null;
  cutoff: string | null;
  basis: string | null;
  currency: string | null;
  acp_provenance: string[];
  qbo_provenance: string[];
  acp_total: string | null;
  qbo_total: string | null;
  difference: string | null;
  acp_total_debits: string | null;
  acp_total_credits: string | null;
  qbo_total_debits: string | null;
  qbo_total_credits: string | null;
  acp_balanced: boolean | null;
  qbo_balanced: boolean | null;
  lines: ReportLineDifference[];
  review_state: string;
  evidence_digest: string;
}

export interface AccountantReviewItem {
  source_domain: string;
  source_reference: string;
  category: string;
  state: string;
  review_requirement: string;
  display_identity: string;
  provenance: string[];
  source_lifecycle: string;
  action_path: string | null;
}

export interface AccountantReviewProjection {
  company_id: string;
  items: AccountantReviewItem[];
  generated_at: string;
}

export interface CloseBlocker {
  code: string;
  family: string;
  state: string;
  explanation: string;
  evidence_reference: string | null;
}

export interface PeriodCloseReadiness {
  period_id: string;
  start_date: string;
  end_date: string;
  lifecycle_status: string;
  accounting_basis: string;
  currency: string;
  opening_equity_readiness: string;
  trial_balance_readiness: string;
  ar_readiness: string;
  ap_readiness: string;
  payroll_readiness: string;
  report_comparison_readiness: string;
  accountant_review_blocker_count: number;
  required_approvals: string[];
  blockers: CloseBlocker[];
  overall_readiness: "READY" | "BLOCKED";
  evidence_digest: string;
  generated_at: string;
}

export async function getReportComparisons(
  periodId: string,
): Promise<ReportComparison[]> {
  return (
    await apiClient.get<ReportComparison[]>(
      `/api/v1/accounting/periods/${periodId}/report-comparisons`,
    )
  ).data;
}

export async function getAccountantReview(): Promise<AccountantReviewProjection> {
  return (
    await apiClient.get<AccountantReviewProjection>(
      "/api/v1/accounting/accountant-review",
    )
  ).data;
}

export async function getPeriodCloseReadiness(
  periodId: string,
): Promise<PeriodCloseReadiness> {
  return (
    await apiClient.get<PeriodCloseReadiness>(
      `/api/v1/accounting/periods/${periodId}/close-readiness`,
    )
  ).data;
}

export async function closeAccountingPeriod(input: {
  periodId: string;
  expectedVersion: number;
  reason: string;
  readinessDigest: string;
}): Promise<AccountingPeriod> {
  return (
    await apiClient.post<AccountingPeriod>(
      `/api/v1/accounting/periods/${input.periodId}/close`,
      {
        expected_version: input.expectedVersion,
        reason: input.reason,
        readiness_digest: input.readinessDigest,
      },
    )
  ).data;
}

export interface OpeningControlDetail {
  package: {
    id: string;
    company_id: string;
    realm_id: string;
    package_identity: string;
    cutoff_at: string;
    status: string;
    evidence_digest: string;
    total_debits: string;
    total_credits: string;
    ar_control_balance: string | null;
    ar_subledger_balance: string | null;
    ap_control_balance: string | null;
    ap_subledger_balance: string | null;
    version: number;
    approved_by_user_id: string | null;
    applied_journal_id: string | null;
  };
  trial_balance: Array<{
    source_identity: string;
    account_type: string;
    equity_category: string | null;
    debit: string;
    credit: string;
    source_version: string;
    source_digest: string;
  }>;
  total_debits: string;
  total_credits: string;
  difference: string;
  equity_categories: string[];
  ar_difference: string | null;
  ap_difference: string | null;
  source_as_of: string;
  cutoff_at: string;
  lifecycle: Array<{
    state: string;
    at: string;
    actor_role: string;
    actor_display_name: string;
  }>;
}

export interface OpeningSubledgerPage {
  package_id: string;
  items: Array<Record<string, unknown>>;
  offset: number;
  limit: number;
  total: number;
}

export async function previewSealedOpening(
  packageIdentity: string,
): Promise<Record<string, unknown>> {
  return (
    await apiClient.post("/api/v1/accounting/opening-controls/sealed-preview", {
      package_identity: packageIdentity,
    })
  ).data;
}

export async function sealOpening(
  packageIdentity: string,
): Promise<Record<string, unknown>> {
  return (
    await apiClient.post("/api/v1/accounting/opening-controls/sealed", {
      package_identity: packageIdentity,
    })
  ).data;
}

export async function getOpeningControlDetail(
  packageId: string,
): Promise<OpeningControlDetail> {
  return (
    await apiClient.get<OpeningControlDetail>(
      `/api/v1/accounting/opening-controls/${packageId}`,
    )
  ).data;
}

export async function getOpeningSubledger(
  packageId: string,
  family: "ar" | "ap",
  offset = 0,
  limit = 100,
): Promise<OpeningSubledgerPage> {
  return (
    await apiClient.get<OpeningSubledgerPage>(
      `/api/v1/accounting/opening-controls/${packageId}/subledger/${family}`,
      { params: { offset, limit } },
    )
  ).data;
}

export interface PayrollAccountingControl {
  cutoff_at: string;
  currency: string;
  status: string;
  evidence_digest: string;
  findings: Array<{
    category: string;
    disposition:
      | "MATCHED"
      | "SOURCE_ONLY"
      | "ACP_ONLY"
      | "AMOUNT_DIFFERENCE"
      | "DATE_CUTOFF_DIFFERENCE"
      | "MISSING_LINK"
      | "REVIEW_REQUIRED";
    payroll_amount: string | null;
    general_ledger_amount: string | null;
    difference: string | null;
    explanation: string;
  }>;
}

export async function getPayrollAccountingControl(
  runId: string,
  cutoffAt: string,
): Promise<PayrollAccountingControl> {
  return (
    await apiClient.get<PayrollAccountingControl>(
      `/api/v1/payroll/operator/accounting-controls/runs/${runId}`,
      { params: { cutoff_at: cutoffAt } },
    )
  ).data;
}
