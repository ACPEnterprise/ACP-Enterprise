import { apiClient } from "./client";

export type QualityState =
  "complete" | "partial" | "stale" | "conflicting" | "unavailable";
export interface EconomicsTotals {
  revenue: number;
  labor: number;
  materials: number;
  equipment: number;
  truck: number;
  overhead: number | null;
  gross_profit: number;
  net_profit: number | null;
}
export interface EconomicsJob {
  result_id: string;
  result_digest: string;
  package_digest: string;
  computation_digest: string;
  authority_state: "current";
  job_id: string;
  job_number: string;
  job_status: string;
  branch_name: string;
  customer_name: string;
  service_category: string | null;
  currency: string;
  revenue_minor: number | null;
  labor_minor: number | null;
  materials_minor: number | null;
  other_direct_cost_minor: number | null;
  contribution_minor: number | null;
  net_profit_minor: number | null;
  margin_basis_points: number | null;
  quality_state: QualityState;
  confidence_percent: number;
  missing_categories: string[];
}
export interface EconomicsRollup {
  label: string;
  jobs: number;
  complete_jobs: number;
  revenue_minor: number;
  contribution_minor: number;
  quality_state: QualityState;
}
export interface EconomicsWorkspace {
  period: { start: string; end: string };
  prior_period: { start: string; end: string };
  quality_state: QualityState;
  currency: string | null;
  source_result_count: number;
  excluded_job_count: number;
  job_count: number;
  complete_job_count: number;
  unclassified_job_count: number;
  totals: EconomicsTotals | null;
  jobs: EconomicsJob[];
  service_categories: EconomicsRollup[];
  customers: EconomicsRollup[];
  branches: EconomicsRollup[];
  fully_allocated_available: boolean;
  explanation: string;
  comparison: {
    state: "available" | "unavailable";
    reason?: string;
    revenue_change_minor?: number;
    contribution_change_minor?: number;
    labor_change_minor?: number;
    materials_change_minor?: number;
    explanation?: string;
  };
  readiness: {
    evidence: string;
    allocation_policy: string;
    attribution: string;
    allocation_authority: {
      state: string;
      pool_policy: string;
      basis_policy: string;
      source_evidence: string;
      supported_basis_types: string[];
      owner_decision: string | null;
      callback_economics: string;
    };
    policy_gaps: { gap_key: string; requirement: string; state: string }[];
  };
  beacon_conditions: { kind: string; state: string }[];
}
export interface EconomicsResultDetail {
  id: string;
  subject_id: string;
  scope: string;
  period_start: string;
  period_end: string;
  currency: string;
  authority_state: "current" | "historical";
  components: Record<
    string,
    {
      state: string;
      amount_minor: number | null;
      confidence_percent: number;
      explanation: string;
      evidence: {
        owner: string;
        source_system: string;
        record_type: string;
        record_id: string;
        content_digest: string;
      }[];
    }
  > | null;
  quality: Record<string, unknown> | null;
  explanation: {
    answer: string;
    findings: { kind: string; summary: string; explanation: string }[];
    limitations: string[];
  } | null;
  lineage: {
    result_digest: string;
    admission_digest: string;
    package_digest: string;
    computation_digest: string;
    acquisition_digests: string[];
    allocation_digests: string[];
    explanation_ids: string[];
    predecessor_result_id: string | null;
    successor_result_id: string | null;
    supersession_reason: string | null;
  };
}
export type OwnerQuestion =
  | "least_profitable_jobs"
  | "most_profitable_jobs"
  | "service_contribution"
  | "branch_contribution"
  | "incomplete_measurements"
  | "what_changed"
  | "margin_leakage"
  | "labor_cost_movement"
  | "material_cost_movement"
  | "full_profitability_blockers"
  | "owner_decisions_required"
  | "inspect_first";
export interface OwnerIntelligenceAnswer {
  contract_version: string;
  question: OwnerQuestion;
  quality_state: QualityState;
  currency: string | null;
  answer: {
    kind: string;
    items?: Array<Record<string, unknown>>;
    comparison?: Record<string, unknown>;
    warning?: string;
  };
  context_packet: {
    evidence_digest: string;
    classification: string;
    completeness: string;
    freshness: string;
    limitations: string[];
    source_references: Array<{
      domain: string;
      entity_type: string;
      entity_id: string;
    }>;
    mutation_authority: "none";
  };
}
export interface CashOperationalEconomics {
  version: string;
  period: { start: string; end: string };
  work_period: {
    state: string;
    currency: string | null;
    earned_revenue_minor: number | null;
    job_contribution_minor: number | null;
    job_count: number;
    complete_job_count: number;
    limitation: string;
  };
  operational_current_state: {
    state: string;
    currency: string | null;
    completed_jobs_with_open_invoice_count: number;
    completed_work_open_commercial_balance_minor: number;
    payment_receipt_count: number;
    payment_receipt_assertion_minor: number;
    deposit_batch_count: number;
    deposit_batch_gross_minor: number;
    open_vendor_obligation_count: number;
    open_vendor_obligation_minor: number;
    vendor_disbursement_count: number;
    vendor_disbursement_minor: number;
    limitations: string[];
  };
  cash_accounting_period: {
    state: string;
    basis: string | null;
    currency: string | null;
    recognized_income_minor: number | null;
    recognized_expense_minor: number | null;
    limitation: string;
  };
  owner_question_battery: Array<{
    question: string;
    answer?: string;
    answer_minor?: number | null;
    state: string;
    truth_plane?: string;
    limitation?: string;
    items?: string[];
  }>;
  projection_digest: string;
  mutation_authority: "none";
}

export interface EconomicsSourceReadiness {
  source: string;
  state:
    | "AVAILABLE"
    | "PARTIAL"
    | "STALE"
    | "CONFLICTING"
    | "POLICY_REQUIRED"
    | "SOURCE_REQUIRED"
    | "EXTERNAL_GATE"
    | "UNAVAILABLE";
  evidence_count: number;
  explanation: string;
}
export interface EconomicsException {
  source: string;
  state: EconomicsSourceReadiness["state"];
  explanation: string;
  owning_domain: string;
  mutation_authority: "none";
}
export interface EconomicsPolicyFamily {
  family_key: string;
  title: string;
  decision_id: string;
  state:
    "CONFIGURED" | "UNCONFIGURED" | "OWNER_DECISION_REQUIRED" | "CONFLICTING";
  current_policy_id: string | null;
  current_version: number | null;
  current_strategy: string | null;
  supported_strategies: string[];
  required_parameter_keys: string[];
  configured_parameter_keys: string[];
  effective_start: string | null;
  policy_digest: string | null;
}
export interface EconomicsPolicyHistory {
  policy_id: string;
  family_key: string;
  version: number;
  strategy: string | null;
  disposition: string;
  lifecycle: string;
  authority_state: "current" | "historical";
  effective_start: string;
  effective_end: string | null;
  supersedes_policy_id: string | null;
  definition_version: string;
  decision_evidence_digest: string;
  policy_digest: string;
}
export interface EconomicsPolicyAdministration {
  version: string;
  company_id: string;
  branch_id: string | null;
  period: { start: string; end: string };
  readiness: {
    sources: EconomicsSourceReadiness[];
    exceptions: EconomicsException[];
    matrix_digest: string;
    complete_for_direct_contribution: boolean;
    complete_for_fully_allocated_profitability: boolean;
    limitations: string[];
  };
  policy_families: EconomicsPolicyFamily[];
  policy_history: EconomicsPolicyHistory[];
  policy_gaps: Array<{
    family_key: string;
    gap_key: string;
    requirement: string;
    state: string;
    authority_dependency: string;
    effective_start: string;
    gap_digest: string;
  }>;
  policy_snapshots: Array<{
    snapshot_id: string;
    subject_identity: string;
    as_of: string;
    policy_count: number;
    deferred_family_keys: string[];
    parameter_gap_count: number;
    definition_version: string;
    snapshot_digest: string;
  }>;
  mutation_authority: "none";
  administration_fingerprint: string;
}
export interface EconomicsResultLineage {
  current_result_id: string;
  results: Array<{
    result_id: string;
    authority_state: "current" | "historical";
    result_digest: string;
    package_digest: string;
    computation_digest: string;
    period_start: string;
    period_end: string;
    currency: string;
    predecessor_result_id: string | null;
    successor_result_id: string | null;
    supersession_reason: string | null;
    limitations: string[];
  }>;
}

export async function getEconomicsWorkspace(start: string, end: string) {
  return (
    await apiClient.get<EconomicsWorkspace>(
      "/api/v1/business-economics/workspace",
      { params: { start, end } },
    )
  ).data;
}
export async function getEconomicsResult(resultId: string) {
  return (
    await apiClient.get<EconomicsResultDetail>(
      `/api/v1/business-economics/results/${resultId}`,
    )
  ).data;
}
export async function getOwnerIntelligence(
  question: OwnerQuestion,
  start: string,
  end: string,
) {
  return (
    await apiClient.get<OwnerIntelligenceAnswer>(
      "/api/v1/business-economics/owner-intelligence",
      { params: { question, start, end } },
    )
  ).data;
}
export async function getCashOperationalEconomics(start: string, end: string) {
  return (
    await apiClient.get<CashOperationalEconomics>(
      "/api/v1/business-economics/cash-operational",
      { params: { start, end } },
    )
  ).data;
}
export async function getEconomicsPolicyAdministration(
  start: string,
  end: string,
) {
  return (
    await apiClient.get<EconomicsPolicyAdministration>(
      "/api/v1/business-economics/administration",
      { params: { start, end } },
    )
  ).data;
}
export async function getEconomicsResultLineage(resultId: string) {
  return (
    await apiClient.get<EconomicsResultLineage>(
      `/api/v1/business-economics/results/${resultId}/lineage`,
    )
  ).data;
}
