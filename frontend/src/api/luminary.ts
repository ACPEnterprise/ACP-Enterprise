import { apiClient } from "./client";

export interface LuminaryObservation {
  metric: string;
  value_minor: number | null;
  currency: string | null;
  unit: string;
  change_minor?: number | null;
}
export interface LuminaryEvidence {
  source_domain: string;
  record_type: string;
  record_id: string;
  digest: string;
}
export interface LuminaryFinding {
  id: string;
  finding_class: string;
  finding_type: string;
  title: string;
  summary: string;
  observations: LuminaryObservation[];
  confidence_percent: number;
  completeness: string;
  freshness: string;
  explanation: string;
  limitations: string[];
  investigate_next: string[];
  evidence: LuminaryEvidence[];
  finding_digest: string;
  supersedes_finding_id: string | null;
}
export interface LuminaryBriefing {
  id: string;
  company_id: string;
  branch_id: string | null;
  period: { start: string; end: string };
  summary: string;
  completeness: string;
  sections: Array<{ name: string; finding_ids: string[] }>;
  briefing_digest: string;
  evidence_package_digest: string;
  supersedes_briefing_id: string | null;
  generated_at: string;
  findings: LuminaryFinding[];
}
export type SourceCompletenessState =
  | "AVAILABLE"
  | "PARTIAL"
  | "STALE"
  | "CONFLICTING"
  | "POLICY_REQUIRED"
  | "EXTERNAL_GATE"
  | "UNAVAILABLE";
export interface SourceCompletenessEntry {
  source: string;
  state: SourceCompletenessState;
  evidence_count: number;
  explanation: string;
}
export interface LuminarySourceReadiness {
  company_id: string;
  branch_id: string | null;
  profitability: {
    version: string;
    quality_state: string;
    matrix_digest: string;
    complete_for_direct_contribution: boolean;
    complete_for_fully_allocated_profitability: boolean;
    sources: SourceCompletenessEntry[];
    limitations: string[];
  };
  sources: Array<{ domain: string; state: string; use: string }>;
  limitations: string[];
}
export interface LuminaryOwnerEconomics {
  contract_version: string;
  company_id: string;
  branch_id: string | null;
  period: { start: string; end: string };
  prior_period: { start: string; end: string } | null;
  generated_at: string;
  currency: string | null;
  readiness: string;
  confidence: { score_percent: number; method: string };
  job_economics: Array<{
    job_id: string;
    job_number: string;
    job_status: string;
    customer: { id: string; name: string };
    branch: { id: string; name: string };
    service_category: string | null;
    readiness: string;
    invoiced_revenue_minor: number | null;
    settlement_applied_minor: number | null;
    accepted_worked_seconds: number | null;
    direct_wage_cost_minor: number | null;
    actual_material_cost_minor: number | null;
    other_direct_cost_minor: number | null;
    direct_contribution_minor: number | null;
    contribution_percent_basis_points: number | null;
    fully_loaded_profit_minor: number | null;
    missing_prerequisites: string[];
    confidence_percent: number;
  }>;
  service_line_economics: Array<{
    service_category: string;
    job_count: number;
    contribution_ready_job_count: number;
    invoiced_revenue_minor: number;
    accepted_worked_seconds: number;
    actual_material_cost_minor: number | null;
    direct_contribution_minor: number | null;
    average_invoiced_ticket_minor: number | null;
    readiness: string;
    missing_prerequisites: string[];
  }>;
  admitted_source_evidence?: {
    authority: string;
    admitted_reference_count: number;
    families: Record<string, { state: string; reference_count: number; limitation: string }>;
    summary?: {
      job_count: number;
      invoiced_revenue_minor: number | null;
      currency: string | null;
      accepted_worked_seconds: number | null;
      material_cost_minor: number | null;
      settlement_applied_minor: number | null;
    };
    evidence_digest: string;
  };
  recommendation_candidates: Array<{
    recommendation_id: string;
    family: string;
    subject: { kind: string; id: string; label: string };
    economic_mechanism: string;
    confidence: number;
    uncertainty: string[];
    alternatives: string[];
    owner_decision_required: string;
    status: string;
  }>;
  facts: Array<{
    family: string;
    metric: string;
    value: number | null;
    units: string;
    currency: string | null;
    authority: string;
    prerequisite_completeness: string;
    as_of: string;
  }>;
  evidence_priority_queue: Array<{
    prerequisite: string;
    affected_job_count: number;
    responsible_domain: string;
    next_safe_step: string;
    economic_unlock: string;
  }>;
  trend_support: {
    state: string;
    authority: string;
    mixed_authority_periods: string;
    comparison: null | {
      state: string;
      basis?: string;
      currency?: string | null;
      reason?: string;
      explanation?: string;
      revenue_change_minor?: number;
      contribution_change_minor?: number;
      labor_change_minor?: number;
      materials_change_minor?: number;
      invoiced_revenue_change_minor?: number;
      current_reference_count?: number;
      prior_reference_count?: number;
    };
  };
  delta_explanation: {
    state: string;
    authority?: string;
    classification?: string;
    headline?: string;
    explanation?: string;
    reason?: string;
    period: { start: string; end: string };
    prior_period: { start: string; end: string } | null;
    scope: { company_id: string; branch_id: string | null };
    as_of: string;
    freshness: string;
    currency?: string | null;
    causality_boundary: string;
    contribution_change_minor?: number;
    contribution_margin_change_basis_points?: number | null;
    explained_change_minor?: number;
    unexplained_change_minor: number | null;
    components: Array<{
      component: string;
      change_minor: number;
      contribution_effect_minor: number | null;
      classification: string;
      authority: string;
    }>;
    evidence_references?: {
      current?: Array<{ result_id: string; result_digest: string }>;
      prior?: Array<{ result_id: string; result_digest: string }>;
    };
    missing_evidence?: string[];
  };
  market_evidence: { state: string; reason: string };
  scenario: null | {
    state: string;
    changed_assumption: { kind: string; change_basis_points: number | null };
    missing_prerequisites: string[];
    deltas?: Record<string, number>;
    hypothetical: true;
    operational_action_occurred: false;
  };
  mutation_authority: "none";
  packet_digest: string;
}
export async function getLuminaryBriefing(start: string, end: string) {
  return (
    await apiClient.get<LuminaryBriefing>("/api/v1/luminary/briefing", {
      params: { start, end },
    })
  ).data;
}
export async function analyzeLuminary(start: string, end: string) {
  return (
    await apiClient.post<LuminaryBriefing>(
      "/api/v1/luminary/analyses",
      undefined,
      { params: { start, end } },
    )
  ).data;
}
export async function getLuminarySourceReadiness(start: string, end: string) {
  return (
    await apiClient.get<LuminarySourceReadiness>(
      "/api/v1/luminary/source-readiness",
      { params: { start, end } },
    )
  ).data;
}
export async function getLuminaryOwnerEconomics(
  start: string,
  end: string,
  scenarioKind?: string,
  changeBasisPoints?: number,
) {
  return (
    await apiClient.get<LuminaryOwnerEconomics>("/api/v1/luminary/owner-economics", {
      params: {
        start,
        end,
        scenario_kind: scenarioKind,
        change_basis_points: scenarioKind ? changeBasisPoints : undefined,
      },
    })
  ).data;
}
