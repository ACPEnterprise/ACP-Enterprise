import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getAccountingPeriods, getOpeningControlDetail, getOpeningSubledger, getPayrollAccountingControl, sealOpening } from "../api/accountingClose";

export const useAccountingPeriods = (enabled = true) =>
  useQuery({
    queryKey: ["accounting", "periods"],
    queryFn: getAccountingPeriods,
    enabled,
  });

export const useOpeningControlDetail = (packageId: string | null, enabled = true) =>
  useQuery({ queryKey: ["accounting", "opening-control", packageId], queryFn: () => getOpeningControlDetail(packageId!), enabled: enabled && Boolean(packageId) });

export const useOpeningSubledger = (packageId: string | null, family: "ar" | "ap", enabled = true) =>
  useQuery({ queryKey: ["accounting", "opening-control", packageId, family], queryFn: () => getOpeningSubledger(packageId!, family), enabled: enabled && Boolean(packageId) });

export const usePayrollAccountingControl = (runId: string | null, cutoffAt: string | null, enabled = true) =>
  useQuery({ queryKey: ["payroll", "accounting-control", runId, cutoffAt], queryFn: () => getPayrollAccountingControl(runId!, cutoffAt!), enabled: enabled && Boolean(runId) && Boolean(cutoffAt) });

export const useSealOpening = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: sealOpening,
    onSuccess: async () => { await client.invalidateQueries({ queryKey: ["accounting", "opening-control"] }); },
  });
};
