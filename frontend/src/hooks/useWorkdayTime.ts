import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getOwnPunchState,
  getOwnTimecard,
  getAdminTimecardReview,
  correctTimeEntry,
  recordOwnPunch,
  type PunchAction,
  type TimeCorrectionInput,
} from "../api/timekeeping";

export const workdayKeys = {
  all: ["workday", "me"] as const,
  state: () => [...workdayKeys.all, "state"] as const,
  timecard: () => [...workdayKeys.all, "timecard"] as const,
  adminReview: () => ["workday", "admin-review"] as const,
};

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
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: workdayKeys.adminReview() });
    },
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
