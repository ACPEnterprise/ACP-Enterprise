import { useCallback, useEffect, useState } from "react";
import { AppState } from "react-native";
import type { EmployeeDay, EmployeeOperationsService } from "../api/employeeOperations";
import { ApiFailure } from "../api/types";
import type { NetworkMonitor } from "../network/networkMonitor";

export type MyDayStatus = "loading" | "ready" | "empty" | "offline" | "not_authorized" | "identity_not_ready" | "session_expired" | "error";

export function useMyDay(service: EmployeeOperationsService, network: NetworkMonitor) {
  const [status, setStatus] = useState<MyDayStatus>("loading");
  const [day, setDay] = useState<EmployeeDay | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const fail = useCallback((error: unknown) => {
    const kind = error instanceof ApiFailure ? error.kind : "unavailable";
    if (kind === "unauthenticated") { setDay(null); setStatus("session_expired"); }
    else if (kind === "forbidden") { setDay(null); setStatus("not_authorized"); }
    else if (kind === "not_ready") { setDay(null); setStatus("identity_not_ready"); }
    else if (kind === "offline") setStatus("offline");
    else setStatus("error");
  }, []);

  const refresh = useCallback(async () => {
    if (!(await network.isConnected())) {
      setStatus("offline");
      return;
    }
    setRefreshing(true);
    try {
      const authoritativeDay = await service.day();
      setDay(authoritativeDay);
      setStatus(authoritativeDay.assignments.length === 0 ? "empty" : "ready");
    } catch (error) {
      fail(error);
    } finally {
      setRefreshing(false);
    }
  }, [fail, network, service]);

  useEffect(() => { void Promise.resolve().then(refresh); }, [refresh]);
  useEffect(() => network.subscribe((connected) => {
    if (connected) void refresh();
    else setStatus("offline");
  }), [network, refresh]);
  useEffect(() => AppState.addEventListener("change", (next) => {
    if (next === "active") void refresh();
  }).remove, [refresh]);

  return { status, day, refreshing, refresh };
}
