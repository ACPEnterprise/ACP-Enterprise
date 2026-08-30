export type Capability = "home.view" | "time.self.view" | "time.self.punch" | "my_day.view" | "jobs.view" | "jobs.execute" | "pay.self.view" | "notifications.view" | "team_time.view";
export const INITIAL_CAPABILITIES: readonly Capability[] = ["home.view", "time.self.view"];
export function can(capabilities: readonly Capability[], capability: Capability): boolean { return capabilities.includes(capability); }
export function capabilitiesFromPermissions(permissionCodes: readonly string[]): Capability[] {
  const capabilities: Capability[] = ["home.view"];
  if (permissionCodes.includes("COMPANY_TIMEKEEPING_OWN_READ")) capabilities.push("time.self.view");
  if (permissionCodes.includes("COMPANY_TIMEKEEPING_OWN_PUNCH")) capabilities.push("time.self.punch");
  if (permissionCodes.includes("COMPANY_EMPLOYEE_OPERATIONS_OWN_DAY_READ")) capabilities.push("my_day.view");
  if (permissionCodes.includes("COMPANY_JOB_READ")) capabilities.push("jobs.view");
  if (permissionCodes.includes("COMPANY_JOB_EXECUTE")) capabilities.push("jobs.execute");
  if (permissionCodes.includes("COMPANY_PAYROLL_STATEMENT_OWN_READ")) capabilities.push("pay.self.view");
  return capabilities;
}
