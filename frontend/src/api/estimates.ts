import { apiClient } from "./client";
import type { Estimate, EstimateDecisionInput, EstimateList, EstimateProposalInput, EstimateTransitionInput } from "../types/estimates";

const root = "/api/v1/estimates";

export async function getEstimate(id: string): Promise<Estimate> {
  return (await apiClient.get<Estimate>(`${root}/${id}`)).data;
}

export async function listEstimates(status?: string, customerId?: string): Promise<EstimateList> {
  return (await apiClient.get<EstimateList>(root, { params: { status: status || undefined, customer_id: customerId } })).data;
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

export async function transitionEstimate(id: string, action: "send" | "view" | "expire", input: EstimateTransitionInput): Promise<Estimate> {
  return (await apiClient.post<Estimate>(`${root}/${id}/${action}`, input)).data;
}

export async function decideEstimate(id: string, action: "approve" | "reject", input: EstimateDecisionInput): Promise<Estimate> {
  return (await apiClient.post<Estimate>(`${root}/${id}/${action}`, input)).data;
}
