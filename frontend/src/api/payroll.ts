import { apiClient } from "./client";

export interface PayrollOperationsSummary {
  run_counts: Record<string, number>;
  member_dispositions: Record<string, number>;
  payment_counts: Record<string, number>;
  remittance_counts: Record<string, number>;
  reporting_counts: Record<string, number>;
  statement_counts: Record<string, number>;
  adjustment_counts: Record<string, number>;
  history_ready: boolean;
  aggregate_approved_gross: string;
  aggregate_approved_net: string;
  blocker_count: number;
  reconciliation_state: string;
  provider_readiness: {
    filing: string;
    payment: string;
    remittance: string;
  };
}

export interface PayrollReportMetadata {
  id: string;
  employee_id: string | null;
  period_identity: string;
  period_kind: string;
  period_start: string;
  period_end: string;
  currency: string | null;
  state: string;
  totals: Record<string, unknown> | null;
  blockers: string[];
  report_digest: string;
}

export interface ComplianceSchemaMetadata {
  id: string;
  jurisdiction_reference: string;
  package_family: string;
  tax_year: number;
  quarter: number | null;
  schema_version: string;
  rule_version: string;
  required_evidence: string[];
  legal_content_slots: string[];
  lifecycle: string;
  schema_digest: string;
}

export interface PayrollPeriodEmployee {
  employee_id: string;
  employee_number: string;
  display_name: string;
  home_branch_id: string | null;
  accepted_minutes: number;
  regular_candidate_minutes: number | null;
  overtime_candidate_minutes: number | null;
  compensation_readiness: string;
  withholding_readiness: string;
  gross_pay_readiness: string;
  exception_codes: string[];
  payroll_review_status: string;
  time_evidence_revision_ids: string[];
}

export interface PayrollPeriodOperations {
  contract_version: string;
  pay_period_id: string;
  period_start: string;
  period_end: string;
  policy_readiness: string;
  employees: PayrollPeriodEmployee[];
  limitations: string[];
}

export interface PayrollRegisterMember {
  employee_id: string;
  employee_number: string;
  employee_name: string;
  status: string;
  blockers: string[];
  accepted_minutes: number | null;
  regular_minutes: number | null;
  overtime_minutes: number | null;
  compensation_authority_id: string | null;
  earnings: Array<Record<string, unknown>>;
  withholdings_deductions_liabilities: Array<Record<string, unknown>>;
  gross: string | null;
  employee_taxes: string | null;
  deductions: string | null;
  net_pay: string | null;
  employer_liabilities: string | null;
  tax_rule_version: string | null;
  money_version: string | null;
  calculation_digest: string | null;
  job_labor_allocation: string | null;
}

export interface PayrollOperatingRegister {
  run_id: string;
  period_start: string;
  period_end: string;
  processing_date: string;
  payday: string;
  lifecycle: string;
  review_state: string;
  currency: string;
  members: PayrollRegisterMember[];
  liability_totals: Record<string, string>;
  manual_tax_filing_payment_required: boolean;
  run_digest: string;
}

export interface PayrollEmployeeSetup {
  employee_id: string;
  employee_name: string;
  employee_number: string;
  readiness: "READY_FOR_PAYROLL" | "BLOCKED_FOR_PAYROLL";
  blockers: string[];
  protected_input_configuration_ready: boolean;
  compensations: Array<Record<string, unknown> & { id: string; lifecycle: string; version: number }>;
  inputs: Array<Record<string, unknown> & { id: string; lifecycle: string; key: string; domain: string; version: number }>;
}

export type CompensationDraft = {
  effective_start: string; effective_end?: string | null; compensation_type: "hourly" | "salaried";
  hourly_rate?: string | null; salary_amount?: string | null; salary_frequency?: string | null;
  worker_class_reference?: string | null; supersedes_authority_id?: string | null; audit_reason: string;
};

export type PayrollInputDraft = {
  domain: "tax" | "deduction" | "employer_contribution"; authority_key: string;
  effective_start: string; effective_end?: string | null; jurisdiction_reference?: string | null;
  applicability?: "required" | "not_applicable";
  calculation_basis?: string | null; priority?: number | null; public_parameters?: Record<string, unknown>;
  protected_values?: Record<string, unknown> | null; supersedes_authority_id?: string | null; audit_reason: string;
};

export async function getPayrollOperationsSummary(): Promise<PayrollOperationsSummary> {
  return (await apiClient.get<PayrollOperationsSummary>("/api/v1/payroll/operations/summary")).data;
}

export async function listPayrollReports(): Promise<PayrollReportMetadata[]> {
  return (await apiClient.get<PayrollReportMetadata[]>("/api/v1/payroll/reporting")).data;
}

export async function listComplianceSchemas(): Promise<ComplianceSchemaMetadata[]> {
  return (await apiClient.get<ComplianceSchemaMetadata[]>("/api/v1/payroll/compliance/schemas")).data;
}

export async function getPayrollPeriodOperations(payPeriodId: string): Promise<PayrollPeriodOperations> {
  return (
    await apiClient.get<PayrollPeriodOperations>(
      `/api/v1/payroll/operations/pay-periods/${payPeriodId}`,
    )
  ).data;
}

export async function listPayrollOperatingRegisters(): Promise<PayrollOperatingRegister[]> {
  return (await apiClient.get<PayrollOperatingRegister[]>("/api/v1/payroll/operations/registers")).data;
}

export async function getPayrollEmployeeSetup(employeeId: string): Promise<PayrollEmployeeSetup> {
  return (await apiClient.get<PayrollEmployeeSetup>(`/api/v1/payroll/setup/employees/${employeeId}`)).data;
}
export async function draftPayrollCompensation(employeeId: string, body: CompensationDraft) {
  return (await apiClient.post(`/api/v1/payroll/setup/employees/${employeeId}/compensations`, body)).data;
}
export async function draftPayrollInput(employeeId: string, body: PayrollInputDraft) {
  return (await apiClient.post(`/api/v1/payroll/setup/employees/${employeeId}/inputs`, body)).data;
}
export async function approvePayrollCompensation(id: string) {
  return (await apiClient.post(`/api/v1/payroll/setup/compensations/${id}/approve`)).data;
}
export async function approvePayrollInput(id: string) {
  return (await apiClient.post(`/api/v1/payroll/setup/inputs/${id}/approve`)).data;
}
