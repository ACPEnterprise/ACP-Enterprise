import type { TechnicianEligibility } from "../../types/dispatch";

export function isDispatchSelectable(technician: TechnicianEligibility): boolean {
  return technician.eligible;
}
