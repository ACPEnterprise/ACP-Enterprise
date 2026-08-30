import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getBeaconSignals,
  recordBeaconLifecycleAction,
  recordBeaconWorkflowAction,
  type BeaconLifecycleAction,
  type BeaconSignal,
  type BeaconWorkflowAction,
} from "../api/beacon";

export function useBeaconSignals(enabled = true) {
  return useQuery({
    queryKey: ["beacon-signals"],
    queryFn: getBeaconSignals,
    refetchInterval: 60_000,
    enabled,
  });
}

export function useBeaconWorkflowActions() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      signal,
      action,
      expectedVersion,
      ownerUserId,
    }: {
      signal: BeaconSignal;
      action: BeaconWorkflowAction;
      expectedVersion?: number;
      ownerUserId?: string;
    }) =>
      recordBeaconWorkflowAction(
        signal,
        action,
        expectedVersion,
        ownerUserId,
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["beacon-signals"] });
    },
  });
}

export function useBeaconLifecycleActions() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      signal,
      action,
      snoozeUntil,
    }: {
      signal: BeaconSignal;
      action: BeaconLifecycleAction;
      snoozeUntil?: string;
    }) => recordBeaconLifecycleAction(signal, action, snoozeUntil),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["beacon-signals"] });
    },
  });
}
