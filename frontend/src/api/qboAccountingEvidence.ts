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

const allAmounts = (value: QboAccountingEvidenceWorkspace): QboAmount[] => [
  ...value.accounts.map((item) => item.balance),
  ...value.invoices.flatMap((item) => [item.total, item.open_balance]),
  ...value.bills.flatMap((item) => [item.total, item.open_balance]),
  value.ar.total_open,
  value.ar.current,
  value.ar.overdue,
  ...value.payments.map((item) => item.amount),
];

export function validateQboAccountingEvidence(
  value: QboAccountingEvidenceWorkspace,
  requestedBasis: "cash" | "accrual",
): QboAccountingEvidenceWorkspace {
  if (
    value.source !== "quickbooks_online" ||
    value.mutation_authority !== "none" ||
    value.accounting_basis !== requestedBasis
  ) {
    throw new Error("QBO evidence authority is invalid.");
  }
  if (
    value.mode === "live" &&
    (value.provider_environment !== "production" ||
      !value.company_identity_sha256 ||
      !value.company_info_verified_at ||
      !value.source_manifest_sha256 ||
      !value.acquired_at)
  ) {
    throw new Error("Live QBO evidence is not verified and sealed.");
  }
  if (
    value.completeness === "complete" &&
    (!value.source_manifest_sha256 || !value.acquired_at)
  ) {
    throw new Error("Complete QBO evidence requires a sealed acquisition.");
  }
  if (
    value.reports.some(
      (report) => report.basis !== null && report.basis !== requestedBasis,
    )
  ) {
    throw new Error("QBO report basis does not match the requested basis.");
  }
  if (
    allAmounts(value).some(
      (item) =>
        (item.amount === null && item.state === "available") ||
        (item.amount !== null && item.state === "unavailable"),
    )
  ) {
    throw new Error("QBO amount availability is inconsistent.");
  }
  if (
    value.conflicts.some(
      (conflict) =>
        new Set(conflict.source_assertions.map((item) => item.source)).size < 2,
    )
  ) {
    throw new Error("Cross-source conflict evidence is incomplete.");
  }
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
