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

export async function getPayrollOperationsSummary(): Promise<PayrollOperationsSummary> {
  return (await apiClient.get<PayrollOperationsSummary>("/api/v1/payroll/operations/summary")).data;
}

export async function listPayrollReports(): Promise<PayrollReportMetadata[]> {
  return (await apiClient.get<PayrollReportMetadata[]>("/api/v1/payroll/reporting")).data;
}

export async function listComplianceSchemas(): Promise<ComplianceSchemaMetadata[]> {
  return (await apiClient.get<ComplianceSchemaMetadata[]>("/api/v1/payroll/compliance/schemas")).data;
}
