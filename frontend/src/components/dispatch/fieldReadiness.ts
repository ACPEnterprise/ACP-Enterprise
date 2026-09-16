import type { TechnicianEligibility } from "../../types/dispatch";

/**
 * Dispatch consumes established Workforce capability evidence. It must not turn an
 * arbitrary office Employee into a field technician as part of assignment.
 */
export function isFieldAssignmentCandidate(technician: TechnicianEligibility) {
  return technician.capability_codes.includes("technician");
}
