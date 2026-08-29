import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "../api/procurementMatching";

export const procurementMatchKeys = {
  all: ["procurement-matching"] as const,
  detail: (id: string) => ["procurement-matching", id] as const,
};

export const useProcurementMatch = (matchId: string) =>
  useQuery({
    queryKey: procurementMatchKeys.detail(matchId),
    queryFn: () => api.getProcurementMatch(matchId),
    enabled: Boolean(matchId),
  });

export function useProcurementMatchMutations() {
  const client = useQueryClient();
  return {
    evaluate: useMutation({
      mutationFn: api.evaluateProcurementMatch,
      onSuccess: (result) =>
        client.setQueryData(procurementMatchKeys.detail(result.id), result),
    }),
    resolve: useMutation({
      mutationFn: api.resolveProcurementMatch,
      onSuccess: (result) =>
        client.setQueryData(procurementMatchKeys.detail(result.id), result),
    }),
  };
}
