import type { AccessibleCompany } from "../auth/companyTypes";
import { apiClient } from "./client";

export async function listAccessibleCompanies(): Promise<AccessibleCompany[]> {
  const response = await apiClient.get<AccessibleCompany[]>("/api/v1/authorization/companies");
  return response.data;
}
