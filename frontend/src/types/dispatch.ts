export interface DispatchCrewMember {
  id: string;
  employee_id: string;
  display_name: string;
  status: string;
  added_at: string;
}
export interface DispatchAssignment {
  id: string;
  appointment_id: string;
  appointment_number: string;
  job_id: string | null;
  company_id: string;
  branch_id: string;
  primary_employee_id: string | null;
  primary_employee_name: string | null;
  status:
    | "proposed"
    | "assigned"
    | "acknowledged"
    | "released"
    | "replaced"
    | "cancelled"
    | "reconciliation_required";
  arrival_state: "pending" | "en_route" | "arrived";
  active_exception_code: DispatchExceptionCode | null;
  assignment_reason: string;
  window_start_at: string;
  window_end_at: string;
  effective_at: string;
  released_at: string | null;
  version: number;
  crew_members: readonly DispatchCrewMember[];
}
export type DispatchExceptionCode =
  | "assignment_ambiguous"
  | "technician_unavailable"
  | "customer_unavailable"
  | "safety_condition"
  | "weather"
  | "other";
export interface DispatchBoardItem {
  appointment_id: string;
  appointment_number: string;
  job_id: string | null;
  branch_id: string;
  status: string;
  window_start_at: string;
  window_end_at: string;
  assignment: DispatchAssignment | null;
}
export interface DispatchBoardPage {
  items: readonly DispatchBoardItem[];
  total_count: number;
}
export interface TechnicianEligibility {
  employee_id: string;
  employee_number: string;
  display_name: string;
  branch_id: string;
  job_title: string | null;
  capability_codes: readonly string[];
  language_codes: readonly string[];
  decision: string;
  reasons: readonly string[];
  availability_confidence: string;
  eligible: boolean;
}
export interface DispatchRecommendationConstraint {
  constraint: string;
  result: "PASS" | "FAIL" | "UNKNOWN";
  explanation: string;
}
export interface DispatchPlacementRecommendation {
  employee_id: string;
  proposed_window: { start_at: string; end_at: string };
  placement_class: string;
  eligible: boolean;
  rank: number | null;
  constraints: readonly DispatchRecommendationConstraint[];
  tradeoffs: readonly string[];
  limitations: readonly string[];
  confidence: string;
}
export interface DispatchRecommendation {
  recommendation_id: string;
  contract_version: string;
  engine_version: string;
  job_id: string;
  company_id: string;
  branch_id: string;
  candidates: readonly DispatchPlacementRecommendation[];
  risk_conditions: readonly Record<string, string>[];
  recovery_options: readonly Record<string, string>[];
  evidence: readonly { authority: string; identity: string; digest: string }[];
  limitations: readonly string[];
  recommendation_digest: string;
  mutation_authority: "none";
}
