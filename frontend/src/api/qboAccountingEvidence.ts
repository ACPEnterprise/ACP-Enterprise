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
  source_company_label: string;
  source_company_id_masked: string;
  provider_authorization: "verified_current" | "unverified";
  evidence_mode: "current_authorized_snapshot" | "historical_snapshot" | "unavailable";
  entity_counts: Record<string, number>;
  page_counts: Record<string, number>;
  catalog_dispositions: Array<Record<string, string>>;
  completeness: "complete" | "partial" | "unavailable";
  accounting_basis: "cash" | "accrual";
  as_of: string | null;
  acquired_at: string | null;
  refresh_state: QboEvidenceState;
  snapshot_id: string | null;
  snapshot_digest: string | null;
  is_live: false;
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

const amounts = (value: QboAccountingEvidenceWorkspace): QboAmount[] => [
  ...value.accounts.map((item) => item.balance),
  ...value.invoices.flatMap((item) => [item.total, item.open_balance]),
  ...value.bills.flatMap((item) => [item.total, item.open_balance]),
  ...value.payments.map((item) => item.amount),
  value.ar.total_open, value.ar.current, value.ar.overdue,
];

export function validateQboAccountingEvidence(value: QboAccountingEvidenceWorkspace, requestedBasis: "cash" | "accrual") {
  if (value.contract_version !== "qbo-accounting-evidence/v1" || value.source !== "quickbooks_online" || value.mutation_authority !== "none" || value.is_live !== false || value.accounting_basis !== requestedBasis)
    throw new Error("QBO evidence authority is invalid.");
  if (value.mode === "live" && (value.provider_authorization !== "verified_current" || value.evidence_mode !== "current_authorized_snapshot" || !value.company_info_verified_at || !value.source_manifest_sha256 || !value.snapshot_digest || !value.acquired_at))
    throw new Error("Current QBO evidence is not verified and sealed.");
  if (value.mode !== "live" && value.provider_authorization === "verified_current")
    throw new Error("QBO provider authority conflicts with evidence mode.");
  if (value.mode === "historical" && (value.evidence_mode !== "historical_snapshot" || value.refresh_state !== "stale"))
    throw new Error("Historical QBO evidence must remain stale.");
  if (value.reports.some((report) => report.basis !== null && report.basis !== requestedBasis))
    throw new Error("QBO report basis does not match the request.");
  if (amounts(value).some((item) => (item.amount === null) === (item.state === "available")))
    throw new Error("QBO amount availability is inconsistent.");
  if (value.conflicts.some((conflict) => new Set(conflict.source_assertions.map((item) => item.source)).size < 2))
    throw new Error("Cross-source conflict evidence is incomplete.");
  return value;
}

export async function getQboAccountingEvidence(
  basis: "cash" | "accrual",
): Promise<QboAccountingEvidenceWorkspace> {
  const value = (
    await apiClient.get<QboAccountingEvidenceWorkspace>(
      "/api/v1/accounting/source-evidence/qbo",
      { params: { basis } },
    )
  ).data;
  return validateQboAccountingEvidence(value, basis);
}
