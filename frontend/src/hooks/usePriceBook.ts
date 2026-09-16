import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "../api/priceBook";

export const priceBookKeys = {
  all: ["price-book"] as const,
  catalog: (branch?: string, filters: Record<string, unknown> = {}) =>
    ["price-book", "catalog", branch, filters] as const,
  candidateReview: (params: Record<string, unknown>) =>
    ["price-book", "candidate-review", params] as const,
};
export function usePriceBook(
  branch?: string,
  enabled = true,
  filters: Parameters<typeof api.getPriceBook>[1] = {},
) {
  return useQuery({
    queryKey: priceBookKeys.catalog(branch, filters),
    queryFn: () => api.getPriceBook(branch, filters),
    enabled,
  });
}
export function useCandidateReview(
  params: Parameters<typeof api.getCandidateReview>[0],
  enabled = true,
) {
  return useQuery({
    queryKey: priceBookKeys.candidateReview(params),
    queryFn: () => api.getCandidateReview(params),
    enabled,
  });
}
export function useActivationReadiness(versionId?: string) {
  return useQuery({
    queryKey: ["price-book", "activation-readiness", versionId],
    queryFn: () => api.getActivationReadiness(versionId!),
    enabled: Boolean(versionId),
  });
}
export function usePriceBookAudit(entityId?: string) {
  return useQuery({
    queryKey: ["price-book", "audit", entityId],
    queryFn: () => api.getPriceBookAudit(entityId!),
    enabled: Boolean(entityId),
  });
}
export function usePriceBookMutations() {
  const client = useQueryClient();
  const refresh = () =>
    client.invalidateQueries({ queryKey: priceBookKeys.all });
  return {
    category: useMutation({
      mutationFn: api.createCategory,
      onSuccess: refresh,
    }),
    tax: useMutation({ mutationFn: api.createTax, onSuccess: refresh }),
    item: useMutation({
      mutationFn: api.createServiceItem,
      onSuccess: refresh,
    }),
    itemUpdate: useMutation({
      mutationFn: ({ itemId, data }: { itemId: string; data: Parameters<typeof api.updateServiceItem>[1] }) =>
        api.updateServiceItem(itemId, data),
      onSuccess: refresh,
    }),
    version: useMutation({
      mutationFn: ({
        itemId,
        data,
      }: {
        itemId: string;
        data: Parameters<typeof api.createPriceVersion>[1];
      }) => api.createPriceVersion(itemId, data),
      onSuccess: refresh,
    }),
    activate: useMutation({
      mutationFn: ({ id, version }: { id: string; version: number }) =>
        api.activatePriceVersion(id, version),
      onSuccess: refresh,
    }),
    optionGroup: useMutation({
      mutationFn: api.createOptionGroup,
      onSuccess: refresh,
    }),
    option: useMutation({
      mutationFn: ({
        groupId,
        data,
      }: {
        groupId: string;
        data: Parameters<typeof api.addOption>[1];
      }) => api.addOption(groupId, data),
      onSuccess: refresh,
    }),
    reviewBatch: useMutation({
      mutationFn: api.createReviewBatch,
      onSuccess: refresh,
    }),
    reviewDecision: useMutation({
      mutationFn: ({
        batchId,
        data,
      }: {
        batchId: string;
        data: Parameters<typeof api.decideReviewBatch>[1];
      }) => api.decideReviewBatch(batchId, data),
      onSuccess: refresh,
    }),
    snapshot: useMutation({
      mutationFn: ({
        itemId,
        data,
      }: {
        itemId: string;
        data: Parameters<typeof api.createCommercialSnapshot>[1];
      }) => api.createCommercialSnapshot(itemId, data),
    }),
    adjustmentProposal: useMutation({
      mutationFn: api.createAdjustmentProposal,
      onSuccess: refresh,
    }),
    adjustmentDecision: useMutation({
      mutationFn: ({ proposalId, data }: { proposalId: string; data: Parameters<typeof api.decideAdjustmentProposal>[1] }) =>
        api.decideAdjustmentProposal(proposalId, data),
      onSuccess: refresh,
    }),
    adjustmentMaterialize: useMutation({
      mutationFn: ({ proposalId, data }: { proposalId: string; data: Parameters<typeof api.materializeAdjustmentProposal>[1] }) =>
        api.materializeAdjustmentProposal(proposalId, data),
      onSuccess: refresh,
    }),
    activationReview: useMutation({
      mutationFn: ({ versionId, decision, expectedVersion, reason }: {
        versionId: string;
        decision: "price" | "tax" | "effective-date" | "activation-authorization";
        expectedVersion: number;
        reason: string;
      }) => api.recordActivationReview(versionId, decision, expectedVersion, reason),
      onSuccess: refresh,
    }),
  };
}
