import { apiClient } from "./client";

export const FACTORY_CONTROL_OVERVIEW_PATH = "/api/v1/platform/factory-control/overview";

export type FactoryGate = {
  code: string;
  kind: "human" | "provider";
  label: string;
  detail?: string | null;
  blocked_lanes: number;
};

export type FactoryLane = {
  lane_id: string;
  worker: "OM1" | "OM2" | "Laptop" | string;
  domain: string;
  state: "active" | "eligible_idle" | "blocked" | "terminal" | string;
  assignment?: string | null;
  priority?: "P0" | "P1" | "P2" | string | null;
  handoff_at?: string | null;
  updated_at: string;
  blocker?: string | null;
};

export type FactoryQueue = {
  queue_id: "OM1E" | "OM2E" | "LaptopE" | string;
  active: number;
  eligible_idle: number;
  blocked: number;
  oldest_handoff_at?: string | null;
};

export type FactoryVelocity = {
  window: "1d" | "3d" | "7d";
  completed: number;
  weighted_progress: number;
};

export type FactoryControlOverview = {
  as_of: string;
  authority_sha: string;
  completion: {
    closed_percent: number;
    engineering_percent: number;
    beta_percent: number;
    owner_percent: number;
    today_weighted_progress: number;
  };
  backlog: { p0: number; p1: number };
  lanes: FactoryLane[];
  queues: FactoryQueue[];
  oldest_handoff?: FactoryLane | null;
  bottleneck?: { label: string; detail?: string | null; lane_id?: string | null } | null;
  gates: FactoryGate[];
  migration: {
    completeness_percent: number;
    complete: number;
    total: number;
    limitations?: string[];
  };
  velocity: FactoryVelocity[];
};

export type FactoryControlFilters = { lane?: string; domain?: string };

export async function getFactoryControlOverview(
  filters: FactoryControlFilters = {},
): Promise<FactoryControlOverview> {
  return (
    await apiClient.get<FactoryControlOverview>(FACTORY_CONTROL_OVERVIEW_PATH, {
      params: {
        lane: filters.lane || undefined,
        domain: filters.domain || undefined,
      },
    })
  ).data;
}
