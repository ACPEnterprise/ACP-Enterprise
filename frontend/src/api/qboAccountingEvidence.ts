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
  ar: { total_open: QboAmount; current: QboAmount; overdue: QboAmount };
  payments: QboPaymentEvidence[];
  reports: QboReportEvidence[];
  conflicts: QboSourceConflict[];
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
