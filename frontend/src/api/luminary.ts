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
  owner_health: {
    revenue_production: OwnerHealthMoneyMeasure & { basis: string };
    economic_contribution: OwnerHealthMoneyMeasure & { formula: string };
    required_economic_burden: OwnerHealthMoneyMeasure & {
      missing_components: string[];
      policy_state: string;
    };
    economic_health: {
      value_basis_points: number | null;
      classification: EvidenceClassification;
      break_even_basis_points: 10000;
      status: string;
      formula: string;
      limitation: string | null;
    };
    cash_health: {
      classification: "UNAVAILABLE";
      separate_from_economic_health: true;
      limitation: string;
    };
  };
  active_reasoning: {
    contribution: {
      state: string;
      value_minor: number | null;
      job_population_coverage_basis_points: number;
      coverage_basis: string;
      ready_job_count: number;
      job_count: number;
    };
    required_burden: {
      state: string;
      value_minor: number | null;
      coverage_basis_points: number | null;
      coverage_limitation: string;
    };
    economic_health: {
      state: string;
      status: string;
      value_basis_points: number | null;
    };
    can_conclude: string[];
    cannot_conclude: string[];
    ranked_evidence_gaps: EvidenceGapReasoning[];
    highest_value_next_action: EvidenceGapReasoning | null;
    ranking_basis: string;
    causality_semantics: Record<string, string>;
  };
  economic_completion_planner: {
    contract_version: "luminary.economic-completion-planner.v1";
    read_only: true;
    period: { start?: string; end?: string };
    summary: {
      complete_category_count: number;
      partial_category_count: number;
      missing_category_count: number;
      total_category_count: number;
    };
    categories: EconomicCompletionCategory[];
    ranked_completion_plan: EconomicCompletionCategory[];
    highest_value_next_completion: EconomicCompletionCategory | null;
    ranking_basis: string[];
    ranking_limit: string;
    owner_confirmed_authority: {
      found: boolean;
      reason: string;
      required_future_contract: string;
    };
    decision_unlock_graph: {
      category_nodes: string[];
      calculation_nodes: string[];
      decision_nodes: string[];
      edges: Array<{ from: string; to: string; relationship: string }>;
    };
  };
  driver_analysis: {
    state: string;
    reason?: string;
    observed_changes: Array<{
      metric: string;
      classification: "OBSERVED_CHANGE";
      current: number;
      prior: number;
      change: number;
      change_basis_points_of_prior: number | null;
      unit: "minor_currency" | "count";
      currency: string | null;
    }>;
    measured_drivers: Array<{
      component: string;
      classification: "MEASURED_DRIVER";
      contribution_effect_minor: number;
      materiality_basis: string;
      causality: "UNPROVEN";
    }>;
    possible_drivers: Array<{ driver: string; classification: string; reason: string }>;
    unproven_causes: Array<{ cause: string; classification: string; reason: string }>;
    unknown_components: string[];
    economic_health?: {
      value_basis_points: number | null;
      distance_from_break_even_basis_points: number | null;
    };
    cash_health?: { state: string; ar_and_collections_included: false; reason: string };
  };
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

export interface EconomicCompletionCategory {
  category: string;
  label: string;
  economic_role: string;
  dependencies: string[];
  sources: string[];
  responsible_parties: string[];
  ui_path: string;
  ui_path_label: string;
  blocked_calculations: string[];
  blocked_decisions: string[];
  unlocks: string[];
  priority_tier: number;
  rank?: number;
  state: "COMPLETE" | "PARTIAL" | "MISSING";
  missing_dependencies: string[];
  affected_job_count: number | null;
  affected_authoritative_revenue_minor: number | null;
  evidence_freshness: string;
  normal_workflow_available: boolean;
  owner_confirmed: {
    supported: false;
    reason: string;
    effective_period: { start?: string; end?: string };
    supersession_behavior: string;
  };
}

interface EvidenceGapReasoning {
  rank: number;
  gap: string;
  evidence_state: string;
  decision_impact: string;
  priority_tier: number;
  affected_job_count: number | null;
  affected_authoritative_revenue_minor: number | null;
  affected_calculations: string[];
  expected_source: string;
  responsible_party: "OWNER" | "ACCOUNTANT" | "SYSTEM" | "PROVIDER";
  ui_path: string;
  ui_path_label: string;
  why_it_matters: string;
  unlocks: string;
  evidence_freshness: string;
  normal_workflow_available: boolean;
  owner_decision_dependency: boolean;
}

type EvidenceClassification = "MEASURED" | "AUTHORITATIVE" | "OWNER_CONFIRMED" | "UNAVAILABLE";
interface OwnerHealthMoneyMeasure {
  value_minor: number | null;
  classification: EvidenceClassification;
  currency: string | null;
  limitation: string | null;
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
