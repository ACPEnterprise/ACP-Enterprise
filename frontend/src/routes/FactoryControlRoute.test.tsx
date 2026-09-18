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
  metrics: { closed_percent: 81, engineering_percent: 76, beta_percent: 63, owner_percent: 54, weighted_delivery_percent: 65, delivery_1d_percent: 5, delivery_3d_percent: 17, delivery_7d_percent: 39, open_defects: 2, open_gates: 1, utilization_percent: 50, pickup_latency_seconds: 3600, queue_depth: 3, oldest_handoff_seconds: 7200, rework_rate_percent: 10, first_pass_yield_percent: 90 },
  lanes: [
    { lane_code: "OM1-A", milestone_code: "RELEASE.1", lifecycle_state: "ELIGIBLE_IDLE", queue_depth: 1, machine: "om1-host", current_assignment: "RELEASE.1", next_queued_item: "SECURITY.2", controlling_enterprise: "OM1E", self_refill_health: "ELIGIBLE_IDLE", idle_duration_seconds: 300, sla_state: "HEALTHY", sla_violations: [], last_event_at: "2026-09-17T19:00:00Z" },
    { lane_code: "OM2-B", milestone_code: "PAYROLL.1", lifecycle_state: "ACTIVE", queue_depth: 2, machine: "om2-host", current_assignment: "PAYROLL.1", next_queued_item: null, controlling_enterprise: "OM2E", self_refill_health: "SELF_REFILL_HEALTHY", idle_duration_seconds: null, sla_state: "HEALTHY", sla_violations: [], last_event_at: "2026-09-17T19:30:00Z" },
  ],
};

function renderRoute(permissions = ["PLATFORM_FACTORY_CONTROL_READ"], entry = "/admin/factory-control") {
  return render(<AuthenticationContext.Provider value={auth(permissions)}><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={[entry]}><FactoryControlRoute /></MemoryRouter></QueryClientProvider></AuthenticationContext.Provider>);
}

describe("FactoryControlRoute", () => {
  it("renders truth-first portfolio, queue, gate, migration, and velocity telemetry", async () => {
    vi.spyOn(api, "getFactoryControlOverview").mockResolvedValue(overview);
    renderRoute();
    expect(await screen.findByRole("heading", { name: "Factory Control" })).toBeVisible();
    expect(screen.getByText("81.0%")).toBeVisible();
    expect(screen.getByText("OM1-A")).toBeVisible();
    expect(screen.getByText("RELEASE.1")).toBeVisible();
    expect(screen.getByText(/First-pass yield/)).toBeVisible();
    expect(screen.getByText(/1d 5.0%/)).toBeVisible();
    expect(screen.queryByRole("button", { name: /dispatch|start|retry|deploy/i })).not.toBeInTheDocument();
  });

  it("passes a lane drilldown and denies tenant Company administrators", async () => {
    const request = vi.spyOn(api, "getFactoryControlOverview").mockResolvedValue(overview);
    const { unmount } = renderRoute(["PLATFORM_FACTORY_CONTROL_READ"], "/admin/factory-control?lane=OM1-A");
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
});
