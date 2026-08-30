import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "../api/estimates";

export const estimateKeys = {
  all: ["estimates"] as const,
  list: (status?: string, customerId?: string) => ["estimates", "list", status ?? "all", customerId ?? "all"] as const,
  detail: (id: string) => ["estimates", id] as const,
  policies: ["estimates", "commercial-policies"] as const,
  followUps: ["estimates", "follow-ups"] as const,
  report: ["estimates", "commercial-report"] as const,
  history: (id: string) => ["estimates", id, "commercial-history"] as const,
};

export function useCommercialPolicies(enabled = true) {
  return useQuery({ queryKey: estimateKeys.policies, queryFn: api.getCommercialPolicies, enabled });
}
export function useEstimateFollowUps(enabled = true) {
  return useQuery({ queryKey: estimateKeys.followUps, queryFn: () => api.listEstimateFollowUps(), enabled });
}
export function useCommercialReport(enabled = true) {
  return useQuery({ queryKey: estimateKeys.report, queryFn: api.getCommercialReport, enabled });
}
export function useCommercialHistory(id: string, enabled = true) {
  return useQuery({ queryKey: estimateKeys.history(id), queryFn: () => api.getCommercialHistory(id), enabled: enabled && Boolean(id) });
}

export function useEstimates(status?: string, customerId?: string, enabled = true) {
  return useQuery({ queryKey: estimateKeys.list(status, customerId), queryFn: () => api.listEstimates(status, customerId), enabled });
}

export function useEstimate(id: string, enabled = true) {
  return useQuery({ queryKey: estimateKeys.detail(id), queryFn: () => api.getEstimate(id), enabled });
}

export function useEstimateMutations() {
  const client = useQueryClient();
  const update = (estimate: Awaited<ReturnType<typeof api.getEstimate>>) => {
    client.setQueryData(estimateKeys.detail(estimate.id), estimate);
    void client.invalidateQueries({ queryKey: estimateKeys.all });
  };
  return {
    create: useMutation({ mutationFn: api.createEstimate, onSuccess: update }),
    revise: useMutation({
      mutationFn: ({ id, input }: { id: string; input: Parameters<typeof api.reviseEstimate>[1] }) => api.reviseEstimate(id, input),
      onSuccess: update,
    }),
    transition: useMutation({ mutationFn: ({ id, action, input }: { id: string; action: "send" | "view" | "expire"; input: Parameters<typeof api.transitionEstimate>[2] }) => api.transitionEstimate(id, action, input), onSuccess: update }),
    decide: useMutation({ mutationFn: ({ id, action, input }: { id: string; action: "approve" | "reject"; input: Parameters<typeof api.decideEstimate>[2] }) => api.decideEstimate(id, action, input), onSuccess: update }),
    configurePolicy: useMutation({ mutationFn: api.configureCommercialPolicy, onSuccess: () => client.invalidateQueries({ queryKey: estimateKeys.policies }) }),
    followUp: useMutation({ mutationFn: ({ id, input }: { id: string; input: Parameters<typeof api.recordEstimateFollowUp>[1] }) => api.recordEstimateFollowUp(id, input), onSuccess: () => client.invalidateQueries({ queryKey: estimateKeys.followUps }) }),
    preparePresentation: useMutation({ mutationFn: ({ id, input }: { id: string; input: Parameters<typeof api.prepareEstimatePresentation>[1] }) => api.prepareEstimatePresentation(id, input) }),
  };
}
