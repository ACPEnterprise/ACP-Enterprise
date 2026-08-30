import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "../api/procurementMatching";

export const procurementMatchKeys = {
  all: ["procurement-matching"] as const,
  detail: (id: string) => ["procurement-matching", id] as const,
  candidates: ["procurement-matching", "candidates"] as const,
  vendorPerformance: (evaluatedAt: string, branchId?: string) =>
    [
      "procurement-matching",
      "vendor-performance",
      evaluatedAt,
      branchId,
    ] as const,
};

export const useProcurementMatchCandidates = () =>
  useQuery({
    queryKey: procurementMatchKeys.candidates,
    queryFn: api.getProcurementMatchCandidates,
  });

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
        Promise.all([
          client.setQueryData(procurementMatchKeys.detail(result.id), result),
          client.invalidateQueries({
            queryKey: procurementMatchKeys.candidates,
          }),
        ]),
    }),
    resolve: useMutation({
      mutationFn: api.resolveProcurementMatch,
      onSuccess: (result) => {
        client.setQueryData(procurementMatchKeys.detail(result.id), result);
        return client.invalidateQueries({
          queryKey: procurementMatchKeys.candidates,
        });
      },
    }),
  };
}

export const useVendorPerformance = (
  evaluatedAt: string,
  branchId: string | undefined,
  enabled: boolean,
) =>
  useQuery({
    queryKey: procurementMatchKeys.vendorPerformance(evaluatedAt, branchId),
    queryFn: () => api.getVendorPerformance(evaluatedAt, branchId),
    enabled: enabled && Boolean(evaluatedAt),
  });
