export type Capability = "home.view" | "time.self.view" | "time.self.punch" | "my_day.view" | "jobs.view" | "jobs.execute" | "pay.self.view" | "assets.view" | "estimates.view" | "job.sources.view" | "price_book.view" | "invoices.view" | "payments.view" | "communications.view" | "notifications.view" | "team_time.view" | "lia.view";
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
  if (permissionCodes.includes("COMPANY_ASSET_READ")) capabilities.push("assets.view");
  if (permissionCodes.includes("COMPANY_ESTIMATE_READ")) capabilities.push("estimates.view");
  if (permissionCodes.includes("COMPANY_INVOICE_READ")) capabilities.push("invoices.view");
  if (permissionCodes.includes("COMPANY_PAYMENT_READ")) capabilities.push("payments.view");
  if (permissionCodes.includes("COMPANY_COMMUNICATIONS_READ")) capabilities.push("communications.view");
  if (permissionCodes.includes("COMPANY_PRICE_BOOK_READ")) capabilities.push("price_book.view");
  if (permissionCodes.includes("COMPANY_EMPLOYEE_OPERATIONS_OWN_LIA_READ")) capabilities.push("lia.view");
  if (["COMPANY_JOB_READ", "COMPANY_CUSTOMER_READ", "COMPANY_INVOICE_READ", "COMPANY_PAYMENT_READ", "COMPANY_COMMUNICATIONS_READ"].every((permission) => permissionCodes.includes(permission))) capabilities.push("job.sources.view");
  return capabilities;
}
