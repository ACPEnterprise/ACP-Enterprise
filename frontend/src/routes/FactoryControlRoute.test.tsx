import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import * as api from "../api/factoryControl";
import { AuthenticationContext, type AuthenticationContextValue } from "../auth/AuthenticationContext";
import { FactoryControlRoute } from "./FactoryControlRoute";

const auth = (permissions: string[]) => ({
  status: "authenticated", activeCompany: null, user: null, permissionCodes: permissions,
  signIn: vi.fn(), signOut: vi.fn(), refresh: vi.fn(), requireReauthentication: vi.fn(),
}) as unknown as AuthenticationContextValue;

const overview: api.FactoryControlOverview = {
  generated_at: "2026-09-17T20:00:00Z", roadmap_digest: "b".repeat(64), roadmap_milestones: 100,
  p0_backlog: 2, p1_backlog: 4, human_gates: 1, provider_gates: 1, owner_actions: [],
  telemetry_freshness: "LIVE", lifecycle_counts: { ACTIVE: 3, CLOSED: 81 },
  latest_snapshot_at: "2026-09-17T19:59:00Z", last_controller_ingestion_at: "2026-09-17T19:58:00Z",
  active_p0: [{ milestone_code: "PAYROLL.1", title: "Payroll", priority: "P0", lifecycle_status: "ACTIVE", engineering_status: "ACTIVE", owner_acceptance_status: "BLOCKED", next_admissible_action: "Finish Payroll." }],
  active_p1: [], current_bottleneck: { milestone_code: "PAYROLL.1", title: "Payroll", priority: "P0", lifecycle_status: "ACTIVE", engineering_status: "ACTIVE", owner_acceptance_status: "BLOCKED", next_admissible_action: "Finish Payroll." },
  recent_movements: [{ id: "event-1", event_type: "engineering_complete", milestone_code: "RELEASE.1", lane_code: "OM1-A", occurred_at: "2026-09-17T19:45:00Z" }],
  real_operational_acceptance: [{ acceptance_id: "ROA-001", surface: "Customers", milestone_code: "CUSTOMERS.1", owner_task: "Refresh source reconciliation.", real_data_required: "Authoritative provider Customers.", current_result: "SERVICE UNREACHABLE.", blocker: "Repair the source reconciliation path.", owning_domain: "OM2-A / Customers", priority: "P0", status: "DEFECT", beta_operable: false, owner_accepted: false, evidence: ["Issue #432"] }],
  metrics: { represented_milestones: 100, superseded_milestones: 0, closed_count: 81, engineering_count: 76, beta_count: 63, owner_count: 54, closed_percent: 81, engineering_percent: 76, beta_percent: 63, owner_percent: 54, engineering_remaining_weight: 24, human_gated_remaining_weight: 10, provider_gated_remaining_weight: 2, weighted_delivery_percent: 65, delivery_1d_percent: 5, delivery_3d_percent: 17, delivery_7d_percent: 39, open_defects: 2, defects_discovered: 4, defects_closed: 2, defects_reopened: 1, open_gates: 1, utilization_percent: 50, effective_utilization_percent: 50, eligible_idle_seconds: 300, pickup_latency_seconds: 3600, domain_pickup_latency_seconds: 1800, release_pickup_latency_seconds: 3600, release_latency_seconds: 900, queue_depth: 3, oldest_handoff_seconds: 7200, rework_rate_percent: 10, first_pass_yield_percent: 90, event_history_status: "MEASURED", lane_history_status: "MEASURED", velocity_history_status: "MEASURED" },
  lanes: [
    { lane_code: "OM1-A", milestone_code: "RELEASE.1", lifecycle_state: "ELIGIBLE_IDLE", queue_depth: 1, machine: "om1-host", current_assignment: "RELEASE.1", next_queued_item: "SECURITY.2", controlling_enterprise: "OM1E", self_refill_health: "ELIGIBLE_IDLE", idle_duration_seconds: 300, sla_state: "HEALTHY", sla_violations: [], last_event_at: "2026-09-17T19:00:00Z" },
    { lane_code: "OM2-B", milestone_code: "PAYROLL.1", lifecycle_state: "ACTIVE", queue_depth: 2, machine: "om2-host", current_assignment: "PAYROLL.1", next_queued_item: null, controlling_enterprise: "OM2E", self_refill_health: "SELF_REFILL_HEALTHY", idle_duration_seconds: null, sla_state: "HEALTHY", sla_violations: [], last_event_at: "2026-09-17T19:30:00Z" },
  ],
};

function renderRoute(permissions = ["PLATFORM_FACTORY_CONTROL_READ"], entry = "/administration/factory-control") {
  return render(<AuthenticationContext.Provider value={auth(permissions)}><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={[entry]}><FactoryControlRoute /></MemoryRouter></QueryClientProvider></AuthenticationContext.Provider>);
}

describe("FactoryControlRoute", () => {
  it("renders truth-first portfolio, queue, gate, migration, and velocity telemetry", async () => {
    vi.spyOn(api, "getFactoryControlOverview").mockResolvedValue(overview);
    renderRoute();
    expect(await screen.findByRole("heading", { name: "Factory Control" })).toBeVisible();
    expect(screen.getByText("81.0% · 81/100")).toBeVisible();
    expect(screen.getByText("OM1-A")).toBeVisible();
    expect(screen.getByText("RELEASE.1")).toBeVisible();
    expect(screen.getByText(/Reopened: 1/)).toBeVisible();
    expect(screen.getByText(/1d 5.0%/)).toBeVisible();
    expect(screen.getByRole("heading", { name: "Real Operational Acceptance" })).toBeVisible();
    expect(screen.getByText("SERVICE UNREACHABLE.")).toBeVisible();
    expect(screen.queryByRole("button", { name: /dispatch|start|retry|deploy/i })).not.toBeInTheDocument();
  });

  it("passes a lane drilldown and denies tenant Company administrators", async () => {
    const request = vi.spyOn(api, "getFactoryControlOverview").mockResolvedValue(overview);
    const { unmount } = renderRoute(["PLATFORM_FACTORY_CONTROL_READ"], "/administration/factory-control?lane=OM1-A");
    expect(await screen.findByText(/Showing lane OM1-A/)).toBeVisible();
    const authorizedRequestCount = request.mock.calls.length;
    expect(authorizedRequestCount).toBeGreaterThan(0);
    unmount();
    renderRoute(["COMPANY_ADMINISTER"]);
    expect(screen.getByText("Platform owner or administrator authority is required.")).toBeVisible();
    expect(request).toHaveBeenCalledTimes(authorizedRequestCount);
  });

  it("does not invent telemetry when the endpoint is unavailable", async () => {
    vi.spyOn(api, "getFactoryControlOverview").mockRejectedValue(new Error("protected detail"));
    renderRoute();
    expect(await screen.findByText(/No progress or health values were inferred/)).toBeVisible();
    expect(screen.queryByText("protected detail")).not.toBeInTheDocument();
  });

  it("labels empty durable telemetry as not yet measured instead of zero activity", async () => {
    vi.spyOn(api, "getFactoryControlOverview").mockResolvedValue({
      ...overview,
      telemetry_freshness: "NOT_YET_MEASURED",
      lanes: [],
      recent_movements: [],
      metrics: {
        ...overview.metrics,
        open_defects: 0,
        open_gates: 0,
        queue_depth: 0,
        utilization_percent: 0,
        effective_utilization_percent: 0,
        event_history_status: "NOT_YET_MEASURED",
        lane_history_status: "NOT_YET_MEASURED",
        velocity_history_status: "NOT_YET_MEASURED",
      },
    });
    renderRoute();
    expect(await screen.findByText(/Event telemetry not yet measured/)).toBeVisible();
    expect(screen.getByText("Worker lane telemetry is not yet measured.")).toBeVisible();
    expect(screen.getAllByText("Not yet measured").length).toBeGreaterThan(3);
  });

  it("warns when controller telemetry exceeds the live synchronization window", async () => {
    vi.spyOn(api, "getFactoryControlOverview").mockResolvedValue({
      ...overview,
      telemetry_freshness: "STALE",
    });
    renderRoute();
    expect(await screen.findByText(/Factory telemetry is stale/)).toBeVisible();
    expect(screen.getByText("Telemetry STALE")).toBeVisible();
  });
});
