import { apiClient } from "./client";
import type { Estimate, EstimateProposalInput } from "../types/estimates";

const root = "/api/v1/estimates";

export async function getEstimate(id: string): Promise<Estimate> {
  return (await apiClient.get<Estimate>(`${root}/${id}`)).data;
}

export async function createEstimate(input: EstimateProposalInput): Promise<Estimate> {
  return (await apiClient.post<Estimate>(root, input)).data;
}

export async function reviseEstimate(
  id: string,
  input: EstimateProposalInput & { expected_version: number },
): Promise<Estimate> {
  return (await apiClient.post<Estimate>(`${root}/${id}/revisions`, input)).data;
}
