import { useCallback, useEffect, useState } from "react";
import { AppState } from "react-native";
import type { DayAssignment, EmployeeOperationsService } from "../api/employeeOperations";
import { ApiFailure } from "../api/types";
import type { NetworkMonitor } from "../network/networkMonitor";

export type AssignmentDetailStatus = "loading" | "ready" | "offline" | "not_authorized" | "identity_not_ready" | "session_expired" | "not_available" | "error";

export function useAssignmentDetail(service: EmployeeOperationsService, network: NetworkMonitor, appointmentId: string, initialAssignment: DayAssignment | null) {
  const [assignment, setAssignment] = useState<DayAssignment | null>(initialAssignment);
  const [timezone, setTimezone] = useState<string | null>(null);
  const [status, setStatus] = useState<AssignmentDetailStatus>(initialAssignment ? "ready" : "loading");
  const [refreshing, setRefreshing] = useState(false);

  const fail = useCallback((error: unknown) => {
    const kind = error instanceof ApiFailure ? error.kind : "unavailable";
    if (kind === "unauthenticated") { setAssignment(null); setStatus("session_expired"); }
    else if (kind === "forbidden") { setAssignment(null); setStatus("not_authorized"); }
    else if (kind === "not_ready") { setAssignment(null); setStatus("identity_not_ready"); }
    else if (kind === "offline") setStatus("offline");
    else setStatus("error");
  }, []);

  const refresh = useCallback(async () => {
    if (!(await network.isConnected())) { setStatus("offline"); return; }
    setRefreshing(true);
    try {
      const day = await service.day();
      const confirmed = day.assignments.find((item) => item.appointment_id === appointmentId) ?? null;
      setTimezone(day.timezone);
      setAssignment(confirmed);
      setStatus(confirmed ? "ready" : "not_available");
    } catch (error) {
      fail(error);
    } finally {
      setRefreshing(false);
    }
  }, [appointmentId, fail, network, service]);

  useEffect(() => { void Promise.resolve().then(refresh); }, [refresh]);
  useEffect(() => network.subscribe((connected) => { if (connected) void refresh(); else setStatus("offline"); }), [network, refresh]);
  useEffect(() => AppState.addEventListener("change", (next) => { if (next === "active") void refresh(); }).remove, [refresh]);

  return { assignment, timezone, status, refreshing, refresh };
}
