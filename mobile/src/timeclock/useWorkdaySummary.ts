import { useCallback, useEffect, useState } from "react";
import { AppState } from "react-native";
import type { PunchState, TimekeepingService } from "../api/timekeeping";
import { ApiFailure } from "../api/types";
import type { NetworkMonitor } from "../network/networkMonitor";

export type WorkdaySummaryStatus = "loading" | "ready" | "offline" | "unavailable" | "session_expired";

export function useWorkdaySummary(service: TimekeepingService | undefined, network: NetworkMonitor) {
  const [state, setState] = useState<PunchState | null>(null);
  const [status, setStatus] = useState<WorkdaySummaryStatus>(service ? "loading" : "unavailable");

  const refresh = useCallback(async () => {
    if (!service) return null;
    if (!(await network.isConnected())) { setStatus("offline"); return null; }
    try {
      const next = await service.state();
      setState(next);
      setStatus("ready");
      return next;
    } catch (error) {
      setStatus(error instanceof ApiFailure && error.kind === "unauthenticated" ? "session_expired" : "unavailable");
      return null;
    }
  }, [network, service]);

  useEffect(() => { void Promise.resolve().then(refresh); }, [refresh]);
  useEffect(() => service ? network.subscribe((connected) => { if (connected) void refresh(); else setStatus("offline"); }) : undefined, [network, refresh, service]);
  useEffect(() => service ? AppState.addEventListener("change", (next) => { if (next === "active") void refresh(); }).remove : undefined, [refresh, service]);

  return { state, status, refresh };
}
