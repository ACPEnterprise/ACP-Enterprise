export const COMMAND_CENTER_PERMISSION = "COMPANY_ANALYTICS_READ";
export const OWN_DAY_PERMISSION = "COMPANY_EMPLOYEE_OPERATIONS_OWN_DAY_READ";
export const FIELD_EXECUTION_PERMISSION = "COMPANY_JOB_EXECUTE";

export function isFieldTechnicianProfile(
  permissions: ReadonlySet<string>,
): boolean {
  return (
    permissions.has(OWN_DAY_PERMISSION) &&
    permissions.has(FIELD_EXECUTION_PERMISSION) &&
    !permissions.has(COMMAND_CENTER_PERMISSION) &&
    !permissions.has("COMPANY_DISPATCH_MANAGE") &&
    !permissions.has("COMPANY_WORKFORCE_READ")
  );
}
