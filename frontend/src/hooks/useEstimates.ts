import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "../api/estimates";

export const estimateKeys = {
  all: ["estimates"] as const,
  list: (status?: string, customerId?: string) => ["estimates", "list", status ?? "all", customerId ?? "all"] as const,
  detail: (id: string) => ["estimates", id] as const,
};

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
  };
}
