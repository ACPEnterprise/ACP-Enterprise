import { useQuery } from "@tanstack/react-query";

import { getBeaconSignals } from "../api/beacon";

export function useBeaconSignals() {
  return useQuery({
    queryKey: ["beacon-signals"],
    queryFn: getBeaconSignals,
    refetchInterval: 60_000,
  });
}
