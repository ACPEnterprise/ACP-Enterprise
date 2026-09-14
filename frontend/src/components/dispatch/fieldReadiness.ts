import type { TechnicianEligibility } from "../../types/dispatch";

const fieldReadinessReasons = new Set([
  "missing_workforce_profile",
  "missing_required_capability",
  "availability_unknown",
]);

export function canPrepareFieldReadiness(
  technician: TechnicianEligibility,
  permissionCodes: readonly string[],
) {
  return (
    !technician.eligible &&
    permissionCodes.includes("COMPANY_WORKFORCE_CAPABILITY_MANAGE") &&
    permissionCodes.includes("COMPANY_WORKFORCE_AVAILABILITY_MANAGE") &&
    technician.reasons.every((reason) => fieldReadinessReasons.has(reason))
  );
}
