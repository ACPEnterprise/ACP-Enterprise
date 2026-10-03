import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  closeAccountingPeriod,
  getAccountantReview,
  getAccountingPeriods,
  getOpeningControlDetail,
  getOpeningSubledger,
  getPayrollAccountingControl,
  getPeriodCloseReadiness,
  getReportComparisons,
  sealOpening,
} from "../api/accountingClose";

export const useAccountingPeriods = (enabled = true) =>
  useQuery({
    queryKey: ["accounting", "periods"],
    queryFn: getAccountingPeriods,
    enabled,
  });

export const useReportComparisons = (periodId: string | null, enabled = true) =>
  useQuery({
    queryKey: ["accounting", "period", periodId, "report-comparisons"],
    queryFn: () => getReportComparisons(periodId!),
    enabled: enabled && Boolean(periodId),
  });

export const useAccountantReview = (enabled = true) =>
  useQuery({
    queryKey: ["accounting", "accountant-review"],
    queryFn: getAccountantReview,
    enabled,
  });

export const usePeriodCloseReadiness = (
  periodId: string | null,
  enabled = true,
) =>
  useQuery({
    queryKey: ["accounting", "period", periodId, "close-readiness"],
    queryFn: () => getPeriodCloseReadiness(periodId!),
    enabled: enabled && Boolean(periodId),
    staleTime: 0,
  });

export const useGovernedPeriodClose = () => {
  const client = useQueryClient();
  return useMutation({
    retry: false,
    mutationFn: async (input: {
      periodId: string;
      expectedVersion: number;
      reason: string;
    }) => {
      const readiness = await getPeriodCloseReadiness(input.periodId);
      if (readiness.overall_readiness !== "READY") {
        throw new Error("PERIOD_CLOSE_BLOCKED");
      }
      return closeAccountingPeriod({
        ...input,
        readinessDigest: readiness.evidence_digest,
      });
    },
    onSettled: async (_data, _error, input) => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["accounting", "periods"] }),
        client.invalidateQueries({
          queryKey: ["accounting", "period", input.periodId],
        }),
      ]);
    },
  });
};

export const useOpeningControlDetail = (
  packageId: string | null,
  enabled = true,
) =>
  useQuery({
    queryKey: ["accounting", "opening-control", packageId],
    queryFn: () => getOpeningControlDetail(packageId!),
    enabled: enabled && Boolean(packageId),
  });

export const useOpeningSubledger = (
  packageId: string | null,
  family: "ar" | "ap",
  enabled = true,
) =>
  useQuery({
    queryKey: ["accounting", "opening-control", packageId, family],
    queryFn: () => getOpeningSubledger(packageId!, family),
    enabled: enabled && Boolean(packageId),
  });

export const usePayrollAccountingControl = (
  runId: string | null,
  cutoffAt: string | null,
  enabled = true,
) =>
  useQuery({
    queryKey: ["payroll", "accounting-control", runId, cutoffAt],
    queryFn: () => getPayrollAccountingControl(runId!, cutoffAt!),
    enabled: enabled && Boolean(runId) && Boolean(cutoffAt),
  });

export const useSealOpening = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: sealOpening,
    onSuccess: async () => {
      await client.invalidateQueries({
        queryKey: ["accounting", "opening-control"],
      });
    },
  });
};
