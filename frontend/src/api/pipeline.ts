import { apiClient } from "./client";
import type { Lead, LeadCreate, LeadList } from "../types/pipeline";

export async function listLeads(view: string): Promise<LeadList> {
  const response = await apiClient.get<LeadList>("/api/v1/pipeline", {
    params: { view, limit: 200 },
  });
  return response.data;
}

export async function createLead(payload: LeadCreate): Promise<Lead> {
  const response = await apiClient.post<Lead>("/api/v1/pipeline", payload);
  return response.data;
}

