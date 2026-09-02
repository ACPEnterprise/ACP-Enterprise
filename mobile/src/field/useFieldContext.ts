import { useCallback, useEffect, useRef, useState } from "react";
import type { FieldEquipment, FieldEstimate, FieldReadiness, FieldService } from "../api/fieldService";
import { ApiFailure } from "../api/types";
import type { NetworkMonitor } from "../network/networkMonitor";

type ContextStatus = "idle" | "loading" | "live" | "stale" | "offline" | "denied" | "unavailable";

export function useFieldContext(service: FieldService, network: NetworkMonitor, jobId: string | null, assets: boolean, estimates: boolean) {
  const [equipment, setEquipment] = useState<FieldEquipment | null>(null);
  const [estimate, setEstimate] = useState<FieldEstimate | null>(null);
  const [readiness, setReadiness] = useState<FieldReadiness | null>(null);
  const [status, setStatus] = useState<ContextStatus>("idle");
  const hasConfirmed = useRef(false);
  const refresh = useCallback(async () => {
    if (!jobId || (!assets && !estimates)) return;
    if (!(await network.isConnected())) { setStatus(hasConfirmed.current ? "stale" : "offline"); return; }
    setStatus("loading");
    try {
      const [nextEquipment, nextEstimate, nextReadiness] = await Promise.all([
        assets && service.equipment ? service.equipment(jobId) : Promise.resolve(null),
        estimates && service.estimate ? service.estimate(jobId) : Promise.resolve(null),
        assets && service.readiness ? service.readiness() : Promise.resolve(null),
      ]);
      setEquipment(nextEquipment); setEstimate(nextEstimate); setReadiness(nextReadiness); hasConfirmed.current = true; setStatus("live");
    } catch (error) {
      const denied = error instanceof ApiFailure && (error.kind === "forbidden" || error.kind === "not_found");
      if (denied) { setEquipment(null); setEstimate(null); setReadiness(null); hasConfirmed.current = false; }
      setStatus(denied ? "denied" : hasConfirmed.current ? "stale" : "unavailable");
    }
  }, [assets, estimates, jobId, network, service]);
  useEffect(() => { void Promise.resolve().then(refresh); }, [refresh]);
  useEffect(() => {
    if (!jobId || (!assets && !estimates)) return undefined;
    return network.subscribe((connected) => {
      if (connected) void refresh();
      else setStatus(hasConfirmed.current ? "stale" : "offline");
    });
  }, [assets, estimates, jobId, network, refresh]);
  return { equipment, estimate, readiness, status, refresh };
}
