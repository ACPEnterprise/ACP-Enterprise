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
  account_number: string | null;
  name: string;
  fully_qualified_name: string | null;
  account_type: string;
  account_subtype: string | null;
  active: boolean | null;
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
  report_type: string;
  label: string;
  basis: "cash" | "accrual" | null;
  as_of: string | null;
  start_date: string | null;
  acquired_at: string | null;
  source_digest: string | null;
  state: QboEvidenceState;
  limitation: string | null;
}
export interface QboAccountingEvidenceWorkspace {
  contract_version: string;
  source: "quickbooks_online";
  mode: "live" | "historical" | "blocked";
  provider_environment: "production" | "historical_control";
  company_identity_sha256: string | null;
  realm_company_identity: string | null;
  source_company_label: string;
  source_company_id_masked: string;
  company_info_verified_at: string | null;
  source_manifest_sha256: string | null;
  completeness: "complete" | "partial" | "unavailable";
  accounting_basis: "cash" | "accrual";
  as_of: string | null;
  acquired_at: string | null;
  refresh_state: QboEvidenceState;
  provider_authorization: "verified_current" | "unverified";
  evidence_mode:
    "current_authorized_snapshot" | "historical_snapshot" | "unavailable";
  entity_counts: Record<string, number>;
  page_counts: Record<string, number>;
  catalog_dispositions: Array<{
    entity_kind: string;
    requirement?: string;
    disposition?: string;
    provider_status_classification?: string;
    error_classification?: string;
    observed_at?: string;
  }>;
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
  source: "QuickBooks Online";
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
  source: "QuickBooks Online A/R Aging Summary";
  source_company: string;
  realm_id: string;
  report_date: string;
  currency: string | null;
  source_as_of: string | null;
  acquired_at: string;
  net_open_ar: string;
  includes_customer_credits_and_unapplied_payments: true;
  source_digest: string;
  accepted_as_acp_accounting: false;
  mutation_authority: "none";
}

export interface QboSourceBackedGeneralLedger {
  contract_version: "qbo-source-backed-ledger-period/v1";
  source: "quickbooks_online";
  authority: "qbo_source_reported";
  accepted_as_acp_accounting: false;
  mutation_authority: "none";
  control_id: string;
  registration_sha256: string;
  raw_sha256: string;
  accounting_basis: "cash" | "accrual";
  period: { start_date: string; end_date: string };
  limitations: string[];
  total_count: number;
  limit: number;
  offset: number;
  rows: Array<{
    date: string;
    account: string;
    transaction_type: string;
    counterparty: string | null;
    transaction_number: string | null;
    description: string | null;
    amount: string;
  }>;
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

export async function getQboSourceBackedGeneralLedger(request: {
  startDate: string;
  endDate: string;
  basis: "cash" | "accrual";
  limit: number;
  offset: number;
}): Promise<QboSourceBackedGeneralLedger> {
  return (
    await apiClient.get<QboSourceBackedGeneralLedger>(
      "/api/v1/accounting/source-evidence/qbo/reports/general-ledger",
      {
        params: {
          start_date: request.startDate,
          end_date: request.endDate,
          basis: request.basis,
          limit: request.limit,
          offset: request.offset,
        },
      },
    )
  ).data;
}
