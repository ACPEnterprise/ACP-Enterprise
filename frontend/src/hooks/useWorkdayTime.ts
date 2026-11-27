import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getOwnPunchState,
  getOwnTimecard,
  getAdminTimecardReview,
  approveTimeEntry,
  correctTimeEntry,
  getAdminTimecardOperations,
  getCurrentPayPeriod,
  getPayPeriods,
  createPayPeriod,
  recordOwnPunch,
  submitTimeEntry,
  type PunchAction,
  type TimeCorrectionInput,
  type PayPeriodCreateInput,
} from "../api/timekeeping";

export const workdayKeys = {
  all: ["workday", "me"] as const,
  state: () => [...workdayKeys.all, "state"] as const,
  timecard: () => [...workdayKeys.all, "timecard"] as const,
  adminReview: () => ["workday", "admin-review"] as const,
  adminOperations: (payPeriodId: string | null) => ["workday", "admin-operations", payPeriodId] as const,
  currentPayPeriod: () => ["workday", "current-pay-period"] as const,
  payPeriods: () => ["workday", "pay-periods"] as const,
};

async function refreshSupervisorTimeAuthority(client: ReturnType<typeof useQueryClient>) {
  await Promise.all([
    client.invalidateQueries({ queryKey: workdayKeys.adminReview() }),
    client.invalidateQueries({ queryKey: ["workday", "admin-operations"] }),
    client.invalidateQueries({ queryKey: ["payroll"] }),
  ]);
}

export function useOwnWorkdayState(enabled = true) {
  return useQuery({
    queryKey: workdayKeys.state(),
    queryFn: getOwnPunchState,
    enabled,
    retry: false,
    refetchOnWindowFocus: true,
  });
}

export function useTimeCorrection() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ revisionId, input }: { revisionId: string; input: TimeCorrectionInput }) => correctTimeEntry(revisionId, input),
    onSettled: async () => refreshSupervisorTimeAuthority(client),
  });
}

export function useSubmitOwnTimeEntry() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: submitTimeEntry,
    onSettled: async () => {
      await client.invalidateQueries({ queryKey: workdayKeys.timecard() });
    },
  });
}

export function useApproveTimeEntry() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: approveTimeEntry,
    onSettled: async () => refreshSupervisorTimeAuthority(client),
  });
}

export function useAdminTimecardReview(enabled = true) {
  return useQuery({
    queryKey: workdayKeys.adminReview(),
    queryFn: getAdminTimecardReview,
    enabled,
    retry: false,
  });
}

export function useCurrentPayPeriod(enabled = true) {
  return useQuery({
    queryKey: workdayKeys.currentPayPeriod(),
    queryFn: getCurrentPayPeriod,
    enabled,
    retry: false,
  });
}

export function usePayPeriods(enabled = true) {
  return useQuery({
    queryKey: workdayKeys.payPeriods(),
    queryFn: getPayPeriods,
    enabled,
    retry: false,
  });
}

export function useCreatePayPeriod() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: PayPeriodCreateInput) => createPayPeriod(input),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: workdayKeys.currentPayPeriod() }),
        client.invalidateQueries({ queryKey: workdayKeys.payPeriods() }),
        client.invalidateQueries({ queryKey: ["payroll"] }),
      ]);
    },
  });
}

export function useAdminTimecardOperations(payPeriodId: string | null, enabled = true) {
  return useQuery({
    queryKey: workdayKeys.adminOperations(payPeriodId),
    queryFn: () => getAdminTimecardOperations(payPeriodId!),
    enabled: enabled && Boolean(payPeriodId),
    retry: false,
  });
}

export function useOwnTimecard(enabled = true) {
  return useQuery({
    queryKey: workdayKeys.timecard(),
    queryFn: getOwnTimecard,
    enabled,
    retry: false,
  });
}

export function useOwnPunch() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (action: PunchAction) => recordOwnPunch(action),
    onSuccess: (result) => {
      client.setQueryData(workdayKeys.state(), result.state);
    },
    onSettled: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: workdayKeys.state() }),
        client.invalidateQueries({ queryKey: workdayKeys.timecard() }),
      ]);
    },
  });
}
