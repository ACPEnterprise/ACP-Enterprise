import { useCallback, useEffect, useState } from "react";
import { AppState } from "react-native";
import type { PayStatement, PayrollService, PayrollStatus } from "../api/payroll";
import { ApiFailure } from "../api/types";
import type { NetworkMonitor } from "../network/networkMonitor";

export type MyPayState = "loading" | "ready" | "empty" | "offline" | "forbidden" | "session_expired" | "error";
export function useMyPay(service: PayrollService, network: NetworkMonitor) {
  const [statements, setStatements] = useState<PayStatement[]>([]); const [payrollStatus, setPayrollStatus] = useState<PayrollStatus | null>(null);
  const [state, setState] = useState<MyPayState>("loading"); const [refreshing, setRefreshing] = useState(false);
  const refresh = useCallback(async () => {
    if (!(await network.isConnected())) { setState("offline"); return; }
    setRefreshing(true);
    try { const [status, values] = await Promise.all([service.status(), service.statements()]); setPayrollStatus(status); setStatements(values); setState(values.length ? "ready" : "empty"); }
    catch (error) { const kind = error instanceof ApiFailure ? error.kind : "unavailable"; if (kind === "offline") setState("offline"); else if (kind === "forbidden") { setStatements([]); setState("forbidden"); } else if (kind === "unauthenticated") { setStatements([]); setState("session_expired"); } else setState("error"); }
    finally { setRefreshing(false); }
  }, [network, service]);
  useEffect(() => { void Promise.resolve().then(refresh); }, [refresh]);
  useEffect(() => network.subscribe((connected) => { if (connected) void refresh(); else setState("offline"); }), [network, refresh]);
  useEffect(() => { const value = AppState.addEventListener("change", (next) => { if (next === "active") void refresh(); }); return () => value.remove(); }, [refresh]);
  return { statements, payrollStatus, state, refreshing, refresh };
}
