import { apiClient } from "./client";

export const FACTORY_CONTROL_OVERVIEW_PATH = "/api/v1/platform/factory-control/overview";

export type FactoryLane = {
  lane_code: string;
  milestone_code?: string | null;
  lifecycle_state: string;
  queue_depth: number;
  machine?: string | null;
  current_assignment?: string | null;
  next_queued_item?: string | null;
  controlling_enterprise?: string | null;
  self_refill_health?: string | null;
  idle_duration_seconds?: number | null;
  sla_state: "HEALTHY" | "VIOLATED" | "NOT_APPLICABLE";
  sla_violations: string[];
  active_since?: string | null;
  last_handoff_at?: string | null;
  last_event_at: string;
};

export type FactoryMetrics = {
  represented_milestones: number;
  superseded_milestones: number;
  engineering_count: number;
  beta_count: number;
  owner_count: number;
  closed_count: number;
  engineering_percent: number;
  beta_percent: number;
  owner_percent: number;
  closed_percent: number;
  engineering_remaining_weight: number;
  human_gated_remaining_weight: number;
  provider_gated_remaining_weight: number;
  weighted_delivery_percent: number;
  delivery_1d_percent: number;
  delivery_3d_percent: number;
  delivery_7d_percent: number;
  open_defects: number;
  defects_discovered: number;
  defects_closed: number;
  defects_reopened: number;
  open_gates: number;
  utilization_percent: number;
  effective_utilization_percent: number;
  eligible_idle_seconds: number;
  pickup_latency_seconds?: number | null;
  domain_pickup_latency_seconds?: number | null;
  release_pickup_latency_seconds?: number | null;
  release_latency_seconds?: number | null;
  queue_depth: number;
  oldest_handoff_seconds?: number | null;
  rework_rate_percent: number;
  first_pass_yield_percent: number;
  event_history_status: "MEASURED" | "NOT_YET_MEASURED";
  lane_history_status: "MEASURED" | "NOT_YET_MEASURED";
  velocity_history_status: "MEASURED" | "NOT_YET_MEASURED";
};

export type FactoryBacklogItem = {
  milestone_code: string;
  title?: string | null;
  priority?: string | null;
  lifecycle_status?: string | null;
  engineering_status?: string | null;
  owner_acceptance_status?: string | null;
  next_admissible_action?: string | null;
};

export type FactoryControlOverview = {
  roadmap_digest: string;
  roadmap_milestones: number;
  metrics: FactoryMetrics;
  lanes: FactoryLane[];
  generated_at: string;
  p0_backlog: number;
  p1_backlog: number;
  human_gates: number;
  provider_gates: number;
  owner_actions: Array<Record<string, unknown>>;
  lifecycle_counts: Record<string, number>;
  active_p0: FactoryBacklogItem[];
  active_p1: FactoryBacklogItem[];
  current_bottleneck?: FactoryBacklogItem | null;
  recent_movements: Array<{
    id: string;
    event_type: string;
    milestone_code?: string | null;
    lane_code: string;
    occurred_at: string;
  }>;
  latest_snapshot_at?: string | null;
  last_controller_ingestion_at?: string | null;
  telemetry_freshness: "LIVE" | "STALE" | "NOT_YET_MEASURED";
};

export type FactoryControlFilters = { lane?: string };

export type FactoryLaneDrilldown = {
  lane: FactoryLane;
  events: Array<{
    id: string;
    milestone_code?: string | null;
    event_type: string;
    lifecycle_state?: string | null;
    occurred_at: string;
    details: Record<string, unknown>;
  }>;
};

export async function getFactoryControlOverview(): Promise<FactoryControlOverview> {
  return (await apiClient.get<FactoryControlOverview>(FACTORY_CONTROL_OVERVIEW_PATH)).data;
}

export async function getFactoryLaneDrilldown(lane: string): Promise<FactoryLaneDrilldown> {
  const encoded = encodeURIComponent(lane);
  return (await apiClient.get<FactoryLaneDrilldown>(`/api/v1/platform/factory-control/lanes/${encoded}`)).data;
}
