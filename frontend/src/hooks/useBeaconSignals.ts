import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getBeaconSignals,
  recordBeaconLifecycleAction,
  type BeaconLifecycleAction,
  type BeaconSignal,
} from "../api/beacon";

export function useBeaconSignals() {
  return useQuery({
    queryKey: ["beacon-signals"],
    queryFn: getBeaconSignals,
    refetchInterval: 60_000,
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
