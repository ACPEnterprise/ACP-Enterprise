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
  readiness: string;
  confidence: { score_percent: number; method: string };
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
