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
}

export async function listWorkforceEmployees(): Promise<WorkforceEmployeeSummary[]> {
  const response = await apiClient.get<{ items: WorkforceEmployeeSummary[] }>("/api/v1/workforce/employees");
  return response.data.items;
}

export async function getWorkforceEmployee(employeeId: string): Promise<WorkforceEmployeeDetail> {
  const response = await apiClient.get<WorkforceEmployeeDetail>(`/api/v1/workforce/employees/${employeeId}`);
  return response.data;
}
