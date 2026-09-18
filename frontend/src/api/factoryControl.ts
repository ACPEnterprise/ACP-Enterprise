import { apiClient } from "./client";

export const FACTORY_CONTROL_OVERVIEW_PATH = "/api/v1/platform/factory-control/overview";

export type FactoryLane = {
  lane_code: string;
  milestone_code?: string | null;
  lifecycle_state: string;
  queue_depth: number;
  active_since?: string | null;
  last_handoff_at?: string | null;
  last_event_at: string;
};

export type FactoryMetrics = {
  engineering_percent: number;
  beta_percent: number;
  owner_percent: number;
  closed_percent: number;
  weighted_delivery_percent: number;
  delivery_1d_percent: number;
  delivery_3d_percent: number;
  delivery_7d_percent: number;
  open_defects: number;
  open_gates: number;
  utilization_percent: number;
  pickup_latency_seconds?: number | null;
  queue_depth: number;
  oldest_handoff_seconds?: number | null;
  rework_rate_percent: number;
  first_pass_yield_percent: number;
};

export type FactoryControlOverview = {
  roadmap_digest: string;
  roadmap_milestones: number;
  metrics: FactoryMetrics;
  lanes: FactoryLane[];
  generated_at: string;
};

export type FactoryControlFilters = { lane?: string };

export async function getFactoryControlOverview(): Promise<FactoryControlOverview> {
  return (await apiClient.get<FactoryControlOverview>(FACTORY_CONTROL_OVERVIEW_PATH)).data;
}
