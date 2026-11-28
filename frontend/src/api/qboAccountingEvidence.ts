import { apiClient } from "./client";

export type QboEvidenceState =
  "available" | "partial" | "stale" | "refreshing" | "unavailable";
export interface QboAmount {
  amount: string | null;
  currency: string | null;
  state: QboEvidenceState;
}
export interface QboAccountEvidence {
  source_id: string;
  name: string;
  account_type: string;
  account_subtype: string | null;
  balance: QboAmount;
}
export interface QboInvoiceEvidence {
  source_id: string;
  document_number: string | null;
  customer_label: string | null;
  transaction_date: string | null;
  due_date: string | null;
  source_status: string | null;
  total: QboAmount;
  open_balance: QboAmount;
}
export interface QboBillEvidence {
  source_id: string;
  document_number: string | null;
  vendor_label: string | null;
  transaction_date: string | null;
  due_date: string | null;
  source_status: string | null;
  total: QboAmount;
  open_balance: QboAmount;
}
export interface QboSourceConflict {
  conflict_id: string;
  subject_label: string;
  fact_name: string;
  state: "conflicting" | "unresolved";
  source_assertions: Array<{
    source: "qbo" | "hcp" | "acp";
    value: string | null;
    source_date: string | null;
  }>;
  limitation: string;
  next_action?: string;
  evidence?: Array<{ name: string; value: string }>;
}
export interface QboHistoricalReconciliation {
  state: "RECONCILED_WITH_DISCLOSED_EXCEPTIONS";
  source_record_count: number;
  relationship_id_count: number;
  conflict_count: number;
  customer_count: number;
  invoice_count: number;
  invoice_line_count: number;
  invoice_open_balance: QboAmount;
  payment_count: number;
  payment_total: QboAmount;
  payment_invoice_links: number;
  missing_payment_invoice_links: number;
  unlinked_payment_count: number;
  unlinked_payment_total: QboAmount;
  provider_unapplied_amount: QboAmount;
  controls: Record<string, unknown>;
  mutation_authority: "none";
}
export interface QboPaymentEvidence {
  source_id: string;
  transaction_date: string | null;
  customer_label: string | null;
  source_status: string | null;
  amount: QboAmount;
  application_state: string;
  applied_document_ids: string[];
}
export interface QboReportEvidence {
  report_key: string;
  label: string;
  basis: "cash" | "accrual" | null;
  as_of: string | null;
  state: QboEvidenceState;
  limitation: string | null;
}
export interface QboAccountingEvidenceWorkspace {
  contract_version: string;
  source: "quickbooks_online";
  mode: "live" | "historical" | "blocked";
  provider_environment: "production" | "historical_control";
  company_identity_sha256: string | null;
  company_info_verified_at: string | null;
  source_manifest_sha256: string | null;
  completeness: "complete" | "partial" | "unavailable";
  accounting_basis: "cash" | "accrual";
  as_of: string | null;
  acquired_at: string | null;
  refresh_state: QboEvidenceState;
  snapshot_id: string | null;
  snapshot_digest: string | null;
  limitations: string[];
  accounts: QboAccountEvidence[];
  invoices: QboInvoiceEvidence[];
  bills: QboBillEvidence[];
  ar: {
    total_open: QboAmount;
    invoice_evidence_count: number;
    open_invoice_count: number;
    closed_invoice_count: number;
    current: QboAmount;
    overdue: QboAmount;
  };
  payments: QboPaymentEvidence[];
  reports: QboReportEvidence[];
  conflicts: QboSourceConflict[];
  historical_reconciliation?: QboHistoricalReconciliation;
  mutation_authority: "none";
}

export interface QboSourceBackedReportRow {
  kind: string;
  depth: number;
  values: string[];
}

export interface QboSourceBackedProfitAndLoss {
  contract_version: "qbo-source-backed-financial-report/v1";
  report_type: "profit_and_loss";
  authority: "QBO_SOURCE_BACKED";
  provider_environment: "production";
  source: string;
  source_company: string;
  realm_id: string;
  start_date: string;
  end_date: string;
  accounting_basis: "cash" | "accrual";
  currency: string | null;
  source_as_of: string | null;
  acquired_at: string;
  columns: string[];
  rows: QboSourceBackedReportRow[];
  source_digest: string;
  accepted_as_acp_accounting: false;
  mutation_authority: "none";
}

export interface QboSourceBackedArSummary {
  contract_version: "qbo-source-backed-ar-summary/v1";
  authority: "QBO_SOURCE_BACKED";
  provider_environment: "production";
  source: string;
  source_company: string;
  realm_id: string;
  report_date: string;
  currency: string | null;
  source_as_of: string | null;
  acquired_at: string;
  net_open_ar: string;
  current?: QboAmount;
  overdue?: QboAmount;
  invoice_evidence_count?: number;
  open_invoice_count?: number;
  includes_customer_credits_and_unapplied_payments: boolean;
  source_digest: string;
  source_manifest_sha256?: string;
  limitations?: string[];
  accepted_as_acp_accounting: false;
  mutation_authority: "none";
}

export async function getQboAccountingEvidence(
  basis: "cash" | "accrual",
): Promise<QboAccountingEvidenceWorkspace> {
  return (
    await apiClient.get<QboAccountingEvidenceWorkspace>(
      "/api/v1/accounting/source-evidence/qbo",
      { params: { basis } },
    )
  ).data;
}

export async function getQboSourceBackedProfitAndLoss(request: {
  startDate: string;
  endDate: string;
  basis: "cash" | "accrual";
}): Promise<QboSourceBackedProfitAndLoss> {
  return (
    await apiClient.get<QboSourceBackedProfitAndLoss>(
      "/api/v1/accounting/source-evidence/qbo/reports/profit-and-loss",
      {
        params: {
          start_date: request.startDate,
          end_date: request.endDate,
          basis: request.basis,
        },
      },
    )
  ).data;
}

export async function getQboSourceBackedArSummary(
  reportDate: string,
): Promise<QboSourceBackedArSummary> {
  return (
    await apiClient.get<QboSourceBackedArSummary>(
      "/api/v1/accounting/source-evidence/qbo/reports/aged-receivables",
      { params: { report_date: reportDate } },
    )
  ).data;
}

export interface QboHistoricalDataset {
  key: string;
  label: string;
  category: string;
  source_file: string;
  source_sha256: string;
  source_bytes: number;
  record_count: number;
  starts_on: string | null;
  ends_on: string | null;
}

export interface QboHistoricalCatalog {
  contract_version: "qbo-historical-archive-catalog/v1";
  source_company: string;
  source_cutoff: string;
  source_record_count: number;
  relationship_identity_count: number;
  historical_basis: "cash";
  currency: "USD";
  datasets: QboHistoricalDataset[];
  reconciliation_controls: {
    trial_balance: {
      manual_debits: string;
      manual_credits: string;
      difference: string;
    };
    balance_sheet: {
      assets: string;
      liabilities_plus_equity: string;
      equation_difference: string;
    };
    profit_and_loss: {
      net_income: string;
      provider_difference: string;
    };
    general_ledger: {
      manual_dated_rows: number;
      amount_difference: string;
    };
  };
  exception_count: number;
  exceptions: Array<Record<string, unknown>>;
  limitations: string[];
  mutation_authority: "none";
}

export interface QboHistoricalRecord {
  source_identity: string;
  identity_kind: string;
  record_kind: string;
  dataset: string;
  source_row_number: number;
  transaction_date?: string;
  due_date?: string;
  transaction_type?: string;
  reference?: string;
  name?: string;
  description?: string;
  account?: string;
  split_account?: string;
  amount?: string | number;
  balance?: string | number;
  open_balance?: string | number;
  phone?: string;
  email?: string;
  address?: string;
  account_type?: string;
  account_subtype?: string;
  net_amount?: string | number;
  payment_method?: string;
  status?: string;
}

export interface QboHistoricalSearch {
  contract_version: "qbo-historical-search/v1" | "qbo-historical-payroll/v1";
  kind: string;
  total: number;
  offset: number;
  limit: number;
  records: QboHistoricalRecord[];
  mutation_authority: "none";
}

export type QboHistoricalKind =
  | "all"
  | "account"
  | "customer"
  | "vendor"
  | "invoice"
  | "transaction"
  | "bank_activity"
  | "payroll";

export type QboHistoricalReportType =
  | "profit_and_loss"
  | "balance_sheet"
  | "trial_balance"
  | "general_ledger"
  | "cash_activity";

export interface QboHistoricalReport {
  contract_version: "qbo-historical-report/v1";
  report_type: QboHistoricalReportType;
  title: string;
  basis: "cash";
  currency: "USD";
  start_date: string | null;
  end_date: string | null;
  columns: string[];
  rows: Array<QboHistoricalRecord | { row_number: number; cells: unknown[] }>;
  record_count: number;
  amount_total?: string;
  source_sha256: string;
  source_mode: "sealed_source_report" | "sealed_report_rows";
  requested_period_matches_source?: boolean;
  mutation_authority: "none";
}

export async function getQboHistoricalCatalog(): Promise<QboHistoricalCatalog> {
  return (
    await apiClient.get<QboHistoricalCatalog>(
      "/api/v1/accounting/source-evidence/qbo/historical/catalog",
    )
  ).data;
}

export async function searchQboHistoricalRecords(request: {
  kind: QboHistoricalKind;
  query?: string;
  startDate?: string;
  endDate?: string;
  offset?: number;
  limit?: number;
}): Promise<QboHistoricalSearch> {
  if (request.kind === "payroll") {
    return (
      await apiClient.get<QboHistoricalSearch>(
        "/api/v1/accounting/source-evidence/qbo/historical/payroll",
        {
          params: {
            query: request.query || undefined,
            offset: request.offset ?? 0,
            limit: request.limit ?? 100,
          },
        },
      )
    ).data;
  }
  return (
    await apiClient.get<QboHistoricalSearch>(
      "/api/v1/accounting/source-evidence/qbo/historical/records",
      {
        params: {
          kind: request.kind,
          query: request.query || undefined,
          start_date: request.startDate || undefined,
          end_date: request.endDate || undefined,
          offset: request.offset ?? 0,
          limit: request.limit ?? 100,
        },
      },
    )
  ).data;
}

export async function getQboHistoricalReport(request: {
  report: QboHistoricalReportType;
  startDate?: string;
  endDate?: string;
}): Promise<QboHistoricalReport> {
  return (
    await apiClient.get<QboHistoricalReport>(
      `/api/v1/accounting/source-evidence/qbo/historical/reports/${request.report}`,
      {
        params: {
          start_date: request.startDate || undefined,
          end_date: request.endDate || undefined,
        },
      },
    )
  ).data;
}
