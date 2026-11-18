import { apiClient } from "./client";

export interface CutoverReview {
  review: null | { id: string; version: number; lifecycle: string; proposed_legacy_period_end: string | null; proposed_acp_period_start: string | null; opening_ytd_effective_date: string | null };
  employees: Array<{ id: string; display_name: string; status: string; payroll_classification: string }>;
  facts: Array<{ id: string; employee_id: string | null; fact_key: string; candidate_reference: Record<string, unknown>; candidate_classification: string; action: string; certification_state: string; certifier_role: string; certified_value: string | null }>;
  source_employees_awaiting_binding?: Array<{ source: string | null; source_id: string | null; classification: string }>;
  bridge_periods: Array<{ id: string; period_start: string; period_end: string; pay_date: string; source_type: string; certification_state: string; source_reference: string; coverage_complete: boolean; version: number }>;
}

export interface PayrollCompletionReadiness {
  review_state: string;
  calculation_performed: false;
  payroll_executed: false;
  money_moved: false;
  period_selection_state: string;
  required_bridge_fields: Array<{ key: string; label: string; owner: "owner" | "accountant" }>;
  employees: Array<{ employee_id: string; display_name: string; employment_status: string; operational_reactivation_required: false; bridge_population_state: string; acp_ytd_state: string; final_paper_check_recording: string; bridge_periods: Array<{ bridge_period_id: string; period_start: string; period_end: string; pay_date: string; certification_state: string; present_fact_keys: string[]; missing_fact_keys: string[] }> }>;
  final_check_recording_path: string;
  accounting_requirements: string[];
}

export interface HistoricalWorkforceEmployee {
  employee_id: string;
  employee_number: string;
  display_name: string;
  historical_position: string | null;
  current_status: string;
  employment_status_as_of: string;
  employment_eligible_as_of: boolean;
  hire_date: string | null;
  termination_date: string | null;
  compensation: Array<{ authority_version: number; lifecycle: string; effective_start: string; effective_end: string | null; compensation_type: string; hourly_rate: string | null; salary_amount: string | null; salary_frequency: string | null; additional_earning_types: string[]; recurring_components: Array<Record<string, unknown>>; evidence_digest: string }>;
  time_records: Array<{ work_date: string; state: string; provenance: string; approved_duration_minutes: number | null; evidence_digest: string }>;
  variable_pay_and_deduction_evidence: string[];
  source_provenance: string[];
}

export interface HistoricalWorkforceSource {
  period_start: string;
  period_end: string;
  pay_date: string;
  employees: HistoricalWorkforceEmployee[];
  bridge_periods: Array<{ period_start: string; period_end: string; pay_date: string; source_type: string; source_reference: string; certification_state: string }>;
  sealed_answer_key_excluded: true;
  limitations: string[];
}

export const getCutoverReview = async () => (await apiClient.get<CutoverReview>("/api/v1/payroll/cutover-review")).data;
export const createCutoverReview = async (body: Record<string, unknown>) => (await apiClient.post("/api/v1/payroll/cutover-review", body)).data;
export const writeCutoverFact = async (body: Record<string, unknown>, certify: boolean) => (await apiClient.post(`/api/v1/payroll/cutover-review/${certify ? "certifications" : "facts"}`, body)).data;
export const createBridgePeriod = async (body: Record<string, unknown>) => (await apiClient.post("/api/v1/payroll/cutover-review/bridge-periods", body)).data;
export const writeBridgeFact = async (periodId: string, body: Record<string, unknown>) => (await apiClient.post(`/api/v1/payroll/cutover-review/bridge-periods/${periodId}/facts`, body)).data;
export const certifyBridgePeriod = async (periodId: string, body: { certifier_role: "owner" | "accountant"; expected_version: number; idempotency_key: string }) => (await apiClient.post(`/api/v1/payroll/cutover-review/bridge-periods/${periodId}/certify`, body)).data;
export const getCutoverGates = async () => (await apiClient.get<{status: string; blockers: string[]}>("/api/v1/payroll/cutover-review/gates")).data;
export const getDirectDepositReadiness = async () => (await apiClient.get<{status: string; blockers: string[]; can_initiate_ach: boolean}>("/api/v1/payroll/cutover-review/direct-deposit-readiness")).data;
export const getPayrollCompletionReadiness = async () => (await apiClient.get<PayrollCompletionReadiness>("/api/v1/payroll/cutover-review/completion-readiness")).data;
export const getHistoricalWorkforceSource = async () => (await apiClient.get<HistoricalWorkforceSource>("/api/v1/payroll/cutover-review/historical-workforce?period_start=2026-08-15&period_end=2026-08-21&pay_date=2026-08-28")).data;
