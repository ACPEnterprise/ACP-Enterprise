import type { AccessibleCompany } from "../auth/companyTypes";
import { apiClient } from "./client";

export async function listAccessibleCompanies(): Promise<AccessibleCompany[]> {
  const response = await apiClient.get<AccessibleCompany[]>("/api/v1/authorization/companies");
  return response.data;
}

export async function getEffectiveAuthorization(): Promise<{ permission_codes: string[] }> {
  const response = await apiClient.get<{ permission_codes: string[] }>(
    "/api/v1/authorization/context",
  );
  return response.data;
}
