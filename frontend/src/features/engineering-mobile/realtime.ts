import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { activeCompanyId, apiUrl, authenticatedRequestHeaders, refreshAuthentication } from "../../api/client";
import { mobileEngineeringKeys } from "./hooks";
import type { MobileWorkstreamDetail, MobileWorkstreamPage, MobileWorkstreamRuntimeState, MobileWorkstreamSummary } from "./types";

export interface EngineeringRuntimeEvent {
  event_id: string;
  command_id: string;
  event_type: string;
  runtime_state: MobileWorkstreamRuntimeState | null;
  occurred_at: string;
  notification: string | null;
  notifications: readonly string[];
  runtime_version: number | null;
  worker_health: string | null;
  progress_percent: number | null;
  current_activity: string | null;
  heartbeat_at: string | null;
  heartbeat_age_seconds: number | null;
  acknowledgement_latency_ms: number | null;
  execution_latency_ms: number | null;
  validation_latency_ms: number | null;
  deployment_latency_ms: number | null;
  worker_uptime_seconds: number | null;
  reconnect_count: number;
  current_worker: string | null;
  current_session: string | null;
  worker_available: boolean;
  recovery_state: string | null;
}

function merge<T extends MobileWorkstreamSummary>(item: T, event: EngineeringRuntimeEvent): T {
  if (item.command_id !== event.command_id) return item;
  return {
    ...item,
    pipeline_status: event.runtime_state ?? item.pipeline_status,
    runtime_state: event.runtime_state ?? item.runtime_state,
    runtime_version: event.runtime_version,
    worker_health: event.worker_health,
    progress_percent: event.progress_percent,
    current_activity: event.current_activity,
    heartbeat_at: event.heartbeat_at,
    assigned_worker_id: event.current_worker,
    updated_at: event.occurred_at,
    control_pending: event.event_type === "owner_request",
    acknowledgement_latency_ms: event.acknowledgement_latency_ms,
    execution_latency_ms: event.execution_latency_ms,
    validation_latency_ms: event.validation_latency_ms,
    deployment_latency_ms: event.deployment_latency_ms,
    worker_uptime_seconds: event.worker_uptime_seconds,
    reconnect_count: event.reconnect_count,
  };
}

export function useEngineeringRealtime(): "connecting" | "live" | "recovering" {
  const queryClient = useQueryClient();
  const [state, setState] = useState<"connecting" | "live" | "recovering">("connecting");
  useEffect(() => {
    const companyId = activeCompanyId();
    if (!companyId) return;
    const storageKey = `acp.engineering.resume.${companyId}`;
    let stopped = false;
    let controller: AbortController | undefined;
    let reconnects = 0;

    const connect = async () => {
      while (!stopped) {
        controller = new AbortController();
        const headers = authenticatedRequestHeaders();
        const resume = window.sessionStorage.getItem(storageKey);
        if (resume) headers.set("Last-Event-ID", resume);
        try {
          const response = await fetch(apiUrl("/api/v1/engineering/mobile/events"), { headers, signal: controller.signal });
          if (response.status === 401 && await refreshAuthentication()) continue;
          if (response.status === 409 && resume) {
            window.sessionStorage.removeItem(storageKey);
            setState("recovering");
            continue;
          }
          if (!response.ok || !response.body) throw new Error(`Realtime transport returned ${response.status}`);
          reconnects = 0;
          setState("live");
          const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
          let buffer = "";
          while (!stopped) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += value;
            const frames = buffer.split("\n\n");
            buffer = frames.pop() ?? "";
            for (const frame of frames) {
              const data = frame.split("\n").find((line) => line.startsWith("data: "))?.slice(6);
              if (!data) continue;
              const event = JSON.parse(data) as EngineeringRuntimeEvent;
              if (window.sessionStorage.getItem(storageKey) === event.event_id) continue;
              window.sessionStorage.setItem(storageKey, event.event_id);
              queryClient.setQueriesData<MobileWorkstreamPage>({ queryKey: mobileEngineeringKeys.all }, (page) =>
                page ? {
                  ...page,
                  connectivity: {
                    ...page.connectivity,
                    state: event.worker_available ? "connected" : "disconnected",
                    session_id: event.current_session,
                    heartbeat_at: event.heartbeat_at,
                    last_contact_at: event.occurred_at,
                  },
                  items: page.items.map((item) => merge(item, event)),
                } : page,
              );
              queryClient.setQueryData<MobileWorkstreamDetail>(mobileEngineeringKeys.workstream(event.command_id), (item) =>
                item ? {
                  ...merge(item, event),
                  timeline: item.timeline.some((entry) => entry.event === event.event_type && entry.occurred_at === event.occurred_at)
                    ? item.timeline
                    : [...item.timeline, { event: event.notification ?? event.event_type, occurred_at: event.occurred_at }],
                } : item,
              );
              if (event.notifications.length > 0 || event.event_type === "owner_request") {
                void queryClient.invalidateQueries({ queryKey: mobileEngineeringKeys.notifications() });
                void queryClient.invalidateQueries({ queryKey: mobileEngineeringKeys.approvalQueue() });
              }
            }
          }
        } catch (error) {
          if (stopped || (error instanceof DOMException && error.name === "AbortError")) return;
          reconnects += 1;
          setState("recovering");
          await new Promise((resolve) => window.setTimeout(resolve, Math.min(1000 * 2 ** Math.min(reconnects, 5), 30_000)));
        }
      }
    };
    void connect();
    return () => { stopped = true; controller?.abort(); };
  }, [queryClient]);
  return state;
}
