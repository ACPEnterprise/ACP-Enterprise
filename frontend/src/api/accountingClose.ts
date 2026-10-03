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
  lifecycle: Array<{ state: string; at: string; actor_role: string; actor_display_name: string }>;
}

export interface OpeningSubledgerPage {
  package_id: string;
  items: Array<Record<string, unknown>>;
  offset: number;
  limit: number;
  total: number;
}

export async function previewSealedOpening(packageIdentity: string): Promise<Record<string, unknown>> {
  return (await apiClient.post("/api/v1/accounting/opening-controls/sealed-preview", { package_identity: packageIdentity })).data;
}

export async function sealOpening(packageIdentity: string): Promise<Record<string, unknown>> {
  return (await apiClient.post("/api/v1/accounting/opening-controls/sealed", { package_identity: packageIdentity })).data;
}

export async function getOpeningControlDetail(packageId: string): Promise<OpeningControlDetail> {
  return (await apiClient.get<OpeningControlDetail>(`/api/v1/accounting/opening-controls/${packageId}`)).data;
}

export async function getOpeningSubledger(packageId: string, family: "ar" | "ap", offset = 0, limit = 100): Promise<OpeningSubledgerPage> {
  return (await apiClient.get<OpeningSubledgerPage>(`/api/v1/accounting/opening-controls/${packageId}/subledger/${family}`, { params: { offset, limit } })).data;
}

export interface PayrollAccountingControl {
  cutoff_at: string;
  currency: string;
  status: string;
  evidence_digest: string;
  findings: Array<{
    category: string;
    disposition: "MATCHED" | "SOURCE_ONLY" | "ACP_ONLY" | "AMOUNT_DIFFERENCE" | "DATE_CUTOFF_DIFFERENCE" | "MISSING_LINK" | "REVIEW_REQUIRED";
    payroll_amount: string | null;
    general_ledger_amount: string | null;
    difference: string | null;
    explanation: string;
  }>;
}

export async function getPayrollAccountingControl(runId: string, cutoffAt: string): Promise<PayrollAccountingControl> {
  return (await apiClient.get<PayrollAccountingControl>(`/api/v1/payroll/operator/accounting-controls/runs/${runId}`, { params: { cutoff_at: cutoffAt } })).data;
}
