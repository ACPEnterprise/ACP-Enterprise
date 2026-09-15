import { useCallback, useEffect, useRef, useState } from "react";
import type { FieldEquipment, FieldEstimate, FieldJobSources, FieldPriceBookItem, FieldReadiness, FieldService } from "../api/fieldService";
import { ApiFailure } from "../api/types";
import type { NetworkMonitor } from "../network/networkMonitor";

type ContextStatus = "idle" | "loading" | "live" | "stale" | "offline" | "denied" | "unavailable";

export function useFieldContext(service: FieldService, network: NetworkMonitor, jobId: string | null, assets: boolean, estimates: boolean, sources = false, priceBook = false) {
  const [equipment, setEquipment] = useState<FieldEquipment | null>(null);
  const [estimate, setEstimate] = useState<FieldEstimate | null>(null);
  const [readiness, setReadiness] = useState<FieldReadiness | null>(null);
  const [jobSources, setJobSources] = useState<FieldJobSources | null>(null);
  const [priceBookItems, setPriceBookItems] = useState<FieldPriceBookItem[]>([]);
  const [status, setStatus] = useState<ContextStatus>("idle");
  const hasConfirmed = useRef(false);
  const refresh = useCallback(async () => {
    if (!jobId || (!assets && !estimates && !sources && !priceBook)) return;
    if (!(await network.isConnected())) { setStatus(hasConfirmed.current ? "stale" : "offline"); return; }
    setStatus("loading");
    try {
      const [nextEquipment, nextEstimate, nextReadiness, nextSources, nextPriceBook] = await Promise.all([
        assets && service.equipment ? service.equipment(jobId) : Promise.resolve(null),
        estimates && service.estimate ? service.estimate(jobId) : Promise.resolve(null),
        assets && service.readiness ? service.readiness() : Promise.resolve(null),
        sources && service.sources ? service.sources(jobId) : Promise.resolve(null),
        priceBook && service.priceBook ? service.priceBook(jobId) : Promise.resolve([]),
      ]);
      setEquipment(nextEquipment); setEstimate(nextEstimate); setReadiness(nextReadiness); setJobSources(nextSources); setPriceBookItems(nextPriceBook); hasConfirmed.current = true; setStatus("live");
    } catch (error) {
      const denied = error instanceof ApiFailure && (error.kind === "forbidden" || error.kind === "not_found");
      if (denied) { setEquipment(null); setEstimate(null); setReadiness(null); setJobSources(null); setPriceBookItems([]); hasConfirmed.current = false; }
      setStatus(denied ? "denied" : hasConfirmed.current ? "stale" : "unavailable");
    }
  }, [assets, estimates, jobId, network, priceBook, service, sources]);
  useEffect(() => { void Promise.resolve().then(refresh); }, [refresh]);
  useEffect(() => {
    if (!jobId || (!assets && !estimates && !sources && !priceBook)) return undefined;
    return network.subscribe((connected) => {
      if (connected) void refresh();
      else setStatus(hasConfirmed.current ? "stale" : "offline");
    });
  }, [assets, estimates, jobId, network, priceBook, refresh, sources]);
  return { equipment, estimate, readiness, jobSources, priceBookItems, status, refresh };
}
