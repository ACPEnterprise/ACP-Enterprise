import { apiClient } from "./client";

export interface AccountingAccount {
  id: string;
  company_id: string;
  chart_version_id: string;
  code: string;
  name: string;
  classification: "asset" | "liability" | "equity" | "revenue" | "expense";
  normal_balance: "debit" | "credit";
  status: "active" | "archived";
  effective_from: string;
  effective_to: string | null;
}
export interface AccountingPeriod {
  id: string;
  company_id: string;
  name: string;
  start_date: string;
  end_date: string;
  status: string;
  version: number;
}
export interface JournalLine {
  id: string;
  ordinal: number;
  account_id: string;
  branch_id: string | null;
  debit: string;
  credit: string;
  description: string;
}
export interface AccountingJournal {
  id: string;
  company_id: string;
  period_id: string;
  journal_type: string;
  status: string;
  effective_date: string;
  currency: string;
  description: string;
  total_debits: string;
  total_credits: string;
  source_system: string;
  source_type: string;
  source_identity: string;
  source_digest: string;
  posting_rule_version: string;
  prepared_by_user_id: string;
  approved_by_user_id: string | null;
  posted_at: string | null;
  reversal_of_id: string | null;
  version: number;
  lines: JournalLine[];
}
export interface AccountingOperation {
  id: string;
  company_id: string;
  kind: string;
  reference: string;
  status: string;
  effective_date: string;
  amount: string;
  currency: string;
  journal_id: string | null;
  journal_status: string | null;
  related_operation_id: string | null;
  payload: Record<string, unknown>;
  provenance: Record<string, unknown>;
  created_by_user_id: string;
  created_at: string;
}
export interface AccountingDashboard {
  account_count: number;
  active_account_count: number;
  open_period_count: number;
  close_status: string;
  discrepancy_count: number;
  operation_counts: Record<string, number>;
  trial_balance_debits: string;
  trial_balance_credits: string;
  balanced: boolean;
}

export const getAccountingDashboard = async () =>
  (await apiClient.get<AccountingDashboard>("/api/v1/accounting/dashboard"))
    .data;
export const getAccountingAccounts = async () =>
  (await apiClient.get<AccountingAccount[]>("/api/v1/accounting/accounts"))
    .data;
export const updateAccountingAccountStatus = async (
  id: string,
  status: "active" | "archived",
) =>
  (
    await apiClient.patch<AccountingAccount>(
      `/api/v1/accounting/accounts/${id}/status`,
      { status },
    )
  ).data;
export const getAccountingPeriods = async () =>
  (await apiClient.get<AccountingPeriod[]>("/api/v1/accounting/periods")).data;
export const getAccountingJournals = async () =>
  (await apiClient.get<AccountingJournal[]>("/api/v1/accounting/journals"))
    .data;
export const getAccountingOperations = async () =>
  (await apiClient.get<AccountingOperation[]>("/api/v1/accounting/operations"))
    .data;
export const createAccountingJournal = async (data: Record<string, unknown>) =>
  (await apiClient.post<AccountingJournal>("/api/v1/accounting/journals", data))
    .data;
export const prepareAccountingJournal = async (value: AccountingJournal) =>
  (
    await apiClient.post<AccountingJournal>(
      `/api/v1/accounting/journals/${value.id}/prepare`,
      { expected_version: value.version },
    )
  ).data;
export const approveAccountingJournal = async (
  value: AccountingJournal,
  evidenceDigest: string,
  reason: string,
) =>
  (
    await apiClient.post<AccountingJournal>(
      `/api/v1/accounting/journals/${value.id}/approve`,
      {
        expected_version: value.version,
        evidence_digest: evidenceDigest,
        reason,
      },
    )
  ).data;
export const postAccountingJournal = async (value: AccountingJournal) =>
  (
    await apiClient.post<AccountingJournal>(
      `/api/v1/accounting/journals/${value.id}/post`,
      { expected_version: value.version },
    )
  ).data;
export const createAccountingOperation = async (
  data: Record<string, unknown>,
) =>
  (
    await apiClient.post<AccountingOperation>(
      "/api/v1/accounting/operations",
      data,
    )
  ).data;

export async function evidenceDigest(value: string): Promise<string> {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}
