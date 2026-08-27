import { apiClient } from "./client";

export interface ReportManifest {
  report_name: string;
  definition_version: string;
  currency: string;
  accounting_basis: string;
  timezone: string;
  start_date: string | null;
  as_of_date: string;
  period_status: string | null;
  ledger_cutoff: string;
  contributing_line_count: number;
  checksum: string;
}

export interface ReportQuality {
  completeness: string;
  freshness: string;
  reconciliation: string;
  integrity: string;
  review: string;
  variance: string;
}

export interface ReportScope {
  branch_id: string | null;
  scope_label: string;
  includes_company_unassigned: boolean;
}

export interface AccountBalanceRow {
  account_id: string;
  code: string;
  name: string;
  classification: string;
  beginning_balance: string;
  debits: string;
  credits: string;
  ending_balance: string;
  display_balance: string;
}

export interface TrialBalance {
  scope: ReportScope;
  manifest: ReportManifest;
  quality: ReportQuality;
  rows: AccountBalanceRow[];
  total_beginning_balance: string;
  total_debits: string;
  total_credits: string;
  total_ending_balance: string;
}

export interface StatementRow {
  account_id: string;
  code: string;
  name: string;
  classification: string;
  amount: string;
}

export interface BalanceSheet {
  scope: ReportScope;
  manifest: ReportManifest;
  quality: ReportQuality;
  assets: StatementRow[];
  liabilities: StatementRow[];
  equity: StatementRow[];
  total_assets: string;
  total_liabilities: string;
  total_equity: string;
  current_earnings: string;
  liabilities_equity_and_current_earnings: string;
}

export interface IncomeStatement {
  scope: ReportScope;
  manifest: ReportManifest;
  quality: ReportQuality;
  revenue: StatementRow[];
  expenses: StatementRow[];
  total_revenue: string;
  total_expenses: string;
  net_income: string;
}

export interface GeneralLedgerRow {
  line_id: string;
  journal_id: string;
  account_code: string;
  account_name: string;
  effective_date: string;
  debit: string;
  credit: string;
  running_balance: string;
  source_type: string;
  source_identity: string;
  reversal_of_id: string | null;
}

export interface GeneralLedger {
  scope: ReportScope;
  manifest: ReportManifest;
  quality: ReportQuality;
  beginning_balance: string;
  total_debits: string;
  total_credits: string;
  ending_balance: string;
  rows: GeneralLedgerRow[];
}

export type FinancialReport =
  | TrialBalance
  | BalanceSheet
  | IncomeStatement
  | GeneralLedger;
export type ReportName =
  | "trial-balance"
  | "balance-sheet"
  | "income-statement"
  | "general-ledger";

export interface ReportRequest {
  report: ReportName;
  startDate: string;
  endDate: string;
  branchId?: string;
}

export async function getFinancialReport(
  request: ReportRequest,
): Promise<FinancialReport> {
  const rangeReport =
    request.report === "income-statement" || request.report === "general-ledger";
  const params = {
    ...(rangeReport
      ? { start_date: request.startDate, end_date: request.endDate }
      : { as_of: request.endDate }),
    ...(request.branchId ? { branch_id: request.branchId } : {}),
  };
  return (
    await apiClient.get<FinancialReport>(
      `/api/v1/accounting/reports/${request.report}`,
      { params },
    )
  ).data;
}
