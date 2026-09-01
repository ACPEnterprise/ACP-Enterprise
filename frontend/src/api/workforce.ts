import { apiClient } from "./client";

export interface WorkforceEmployeeSummary {
  employee_id: string;
  employee_number: string;
  display_name: string;
  job_title: string | null;
  employee_type: string;
  employee_status: string;
  home_branch_id: string | null;
  profile_id: string | null;
  profile_status: string | null;
  technician: boolean;
  capability_codes: string[];
  language_codes: string[];
  readiness_state: "READY" | "BLOCKED" | "INSUFFICIENT_EVIDENCE";
  readiness_blockers: string[];
  updated_at: string;
}

export interface WorkforceEmployeeDetail extends WorkforceEmployeeSummary {
  capabilities: Array<{ code: string; display_name: string; proficiency: string; status: string }>;
  certifications: Array<{ code: string; display_name: string; credential_reference: string; status: string; issued_on: string | null; expires_on: string | null }>;
  languages: Array<{ code: string; english_name: string; native_name: string | null; spoken_proficiency: string; customer_facing_eligible: boolean; interpreter_verified: boolean; status: string }>;
  branches: Array<{ branch_id: string; status: string; starts_on: string | null; ends_on: string | null }>;
  work_restrictions: string[];
  equipment_capabilities: Array<{ code: string; display_name: string; proficiency: string; status: string }>;
  availability: Array<{ branch_id: string; start_at: string; end_at: string; status: string; source: string }>;
}

export interface WorkforceEligibilityRequest {
  branch_id: string;
  window_start_at: string;
  window_end_at: string;
  required_capability_codes: string[];
  required_language_codes: string[];
}

export interface WorkforceEligibilityItem {
  employee_id: string;
  employee_number: string;
  display_name: string;
  branch_id: string;
  job_title: string | null;
  capability_codes: string[];
  language_codes: string[];
  decision: string;
  reasons: string[];
  availability_confidence: string;
  eligible: boolean;
}

export interface EmployeePermissionExplanation {
  code: string;
  name: string;
  business_area: string;
  authority: "ROLE_DERIVED" | "OWN_DATA_ONLY" | "DENIED";
  role_codes: string[];
  branch_scoped: boolean;
}

export interface EmployeeAdministrationSummary extends WorkforceEmployeeSummary {
  membership_id: string | null;
  membership_status: string | null;
  user_status: string | null;
  authorization_version: number | null;
  branch_ids: string[];
  role_codes: string[];
  onboarding_status: string | null;
  masked_login: string | null;
  mobile_readiness: "READY" | "BLOCKED" | "NOT_LINKED";
  mobile_readiness_blockers: string[];
}

export interface EmployeeAdministrationDetail extends EmployeeAdministrationSummary {
  permissions: EmployeePermissionExplanation[];
  workforce: WorkforceEmployeeDetail;
}

export async function listWorkforceEmployees(): Promise<WorkforceEmployeeSummary[]> {
  const response = await apiClient.get<{ items: WorkforceEmployeeSummary[] }>("/api/v1/workforce/employees");
  return response.data.items;
}

export async function getWorkforceEmployee(employeeId: string): Promise<WorkforceEmployeeDetail> {
  const response = await apiClient.get<WorkforceEmployeeDetail>(`/api/v1/workforce/employees/${employeeId}`);
  return response.data;
}

export async function evaluateWorkforceEligibility(payload: WorkforceEligibilityRequest): Promise<WorkforceEligibilityItem[]> {
  const response = await apiClient.post<{ items: WorkforceEligibilityItem[] }>("/api/v1/workforce/eligibility", payload);
  return response.data.items;
}

export async function getEmployeeAdministration(
  employeeId: string,
): Promise<EmployeeAdministrationDetail> {
  return (
    await apiClient.get<EmployeeAdministrationDetail>(
      `/api/v1/workforce/administration/employees/${employeeId}`,
    )
  ).data;
}

export async function setEmployeeMembershipStatus(
  membershipId: string,
  status: "active" | "suspended" | "revoked",
): Promise<void> {
  await apiClient.patch(`/api/v1/company-admin/memberships/${membershipId}/status`, {
    status,
  });
}

export async function setEmployeeBranchGrant(
  membershipId: string,
  branchId: string,
  enabled: boolean,
): Promise<void> {
  const path = `/api/v1/company-admin/memberships/${membershipId}/branches/${branchId}`;
  if (enabled) await apiClient.put(path);
  else await apiClient.delete(path);
}

export async function setEmployeeRole(
  membershipId: string,
  roleId: string,
  enabled: boolean,
): Promise<void> {
  const path = `/api/v1/company-admin/memberships/${membershipId}/roles/${roleId}`;
  if (enabled) await apiClient.put(path);
  else await apiClient.delete(path);
}
