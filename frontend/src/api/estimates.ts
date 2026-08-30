import { apiClient } from "./client";
import type { CommercialHistoryItem, CommercialPolicy, CommercialPolicyWrite, CommercialReport, Estimate, EstimateArtifact, EstimateDecisionInput, EstimateFollowUp, EstimateFollowUpWrite, EstimateList, EstimateProposalInput, EstimateTransitionInput, PresentationCredential } from "../types/estimates";

const root = "/api/v1/estimates";

export async function getEstimate(id: string): Promise<Estimate> {
  return (await apiClient.get<Estimate>(`${root}/${id}`)).data;
}

export async function getEstimateArtifact(id: string): Promise<EstimateArtifact> {
  return (await apiClient.get<EstimateArtifact>(`${root}/${id}/artifact`)).data;
}
export async function getCommercialPolicies(): Promise<CommercialPolicy[]> {
  return (await apiClient.get<CommercialPolicy[]>(`${root}/commercial-policies`)).data;
}
export async function configureCommercialPolicy(input: CommercialPolicyWrite): Promise<CommercialPolicy> {
  return (await apiClient.put<CommercialPolicy>(`${root}/commercial-policies`, input)).data;
}
export async function listEstimateFollowUps(state?: string): Promise<EstimateFollowUp[]> {
  return (await apiClient.get<EstimateFollowUp[]>(`${root}/follow-ups`, { params: { state } })).data;
}
export async function getCommercialReport(): Promise<CommercialReport> {
  return (await apiClient.get<CommercialReport>(`${root}/commercial-report`)).data;
}
export async function getCommercialHistory(id: string): Promise<CommercialHistoryItem[]> {
  return (await apiClient.get<CommercialHistoryItem[]>(`${root}/${id}/commercial-history`)).data;
}
export async function recordEstimateFollowUp(id: string, input: EstimateFollowUpWrite): Promise<EstimateFollowUp> {
  return (await apiClient.post<EstimateFollowUp>(`${root}/${id}/follow-ups`, input)).data;
}
export async function prepareEstimatePresentation(id: string, input: { branch_id: string; recipient_reference: string; channel: string; expires_at?: string; idempotency_key: string }): Promise<PresentationCredential> {
  return (await apiClient.post<PresentationCredential>(`${root}/${id}/presentations`, input)).data;
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
