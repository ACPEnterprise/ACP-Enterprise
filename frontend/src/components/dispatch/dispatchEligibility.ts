import type { TechnicianEligibility } from "../../types/dispatch";

export function isDispatchSelectable(
  technician: TechnicianEligibility,
): boolean {
  return technician.eligible;
}

export type DispatchReadiness =
  | "ELIGIBLE"
  | "BRANCH_NOT_READY"
  | "TECHNICIAN_NOT_READY"
  | "CAPABILITY_NOT_READY"
  | "AVAILABILITY_NOT_READY"
  | "INACTIVE";

export function dispatchReadiness(
  technician: TechnicianEligibility,
): DispatchReadiness {
  if (technician.eligible) return "ELIGIBLE";
  const reasons = new Set(technician.reasons);
  if (reasons.has("inactive")) return "INACTIVE";
  if (reasons.has("missing_workforce_profile")) return "TECHNICIAN_NOT_READY";
  if (reasons.has("wrong_branch")) return "BRANCH_NOT_READY";
  if (
    reasons.has("missing_required_capability") ||
    reasons.has("missing_required_language")
  )
    return "CAPABILITY_NOT_READY";
  return "AVAILABILITY_NOT_READY";
}
