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
  as_of: "2026-09-17T20:00:00Z", authority_sha: "b".repeat(40),
  completion: { closed_percent: 81, engineering_percent: 76, beta_percent: 63, owner_percent: 54, today_weighted_progress: 4.5 },
  backlog: { p0: 2, p1: 7 },
  lanes: [
    { lane_id: "OM1-A", worker: "OM1", domain: "release", state: "eligible_idle", assignment: "Release qualification", priority: "P1", updated_at: "2026-09-17T19:00:00Z" },
    { lane_id: "OM2-B", worker: "OM2", domain: "payroll", state: "active", assignment: "Payroll evidence", priority: "P0", updated_at: "2026-09-17T19:30:00Z" },
  ],
  queues: [
    { queue_id: "OM1E", active: 0, eligible_idle: 1, blocked: 0, oldest_handoff_at: "2026-09-17T18:00:00Z" },
    { queue_id: "OM2E", active: 1, eligible_idle: 0, blocked: 1 },
    { queue_id: "LaptopE", active: 1, eligible_idle: 0, blocked: 0 },
  ],
  oldest_handoff: { lane_id: "OM1-A", worker: "OM1", domain: "release", state: "eligible_idle", assignment: "Release qualification", updated_at: "2026-09-17T18:00:00Z", handoff_at: "2026-09-17T18:00:00Z" },
  bottleneck: { label: "Owner acceptance", detail: "Two reviewed decisions remain." },
  gates: [{ code: "OWNER", kind: "human", label: "Owner review", blocked_lanes: 2 }],
  migration: { completeness_percent: 91, complete: 91, total: 100, limitations: ["Seven identities require evidence."] },
  velocity: [{ window: "1d", completed: 4, weighted_progress: 5 }, { window: "3d", completed: 12, weighted_progress: 17 }, { window: "7d", completed: 25, weighted_progress: 39 }],
};

function renderRoute(permissions = ["COMPANY_ADMINISTER"], entry = "/admin/factory-control") {
  return render(<AuthenticationContext.Provider value={auth(permissions)}><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={[entry]}><FactoryControlRoute /></MemoryRouter></QueryClientProvider></AuthenticationContext.Provider>);
}

describe("FactoryControlRoute", () => {
  it("renders truth-first portfolio, queue, gate, migration, and velocity telemetry", async () => {
    vi.spyOn(api, "getFactoryControlOverview").mockResolvedValue(overview);
    renderRoute();
    expect(await screen.findByRole("heading", { name: "Factory Control" })).toBeVisible();
    expect(screen.getByText("81.0%")).toBeVisible();
    expect(screen.getByText("OM1E")).toBeVisible();
    expect(screen.getByText("Owner acceptance")).toBeVisible();
    expect(screen.getByText("91.0%")).toBeVisible();
    expect(screen.getByText("25 completed · 39.0%")).toBeVisible();
    expect(screen.queryByRole("button", { name: /dispatch|start|retry|deploy/i })).not.toBeInTheDocument();
  });

  it("passes a lane drilldown and denies users without Company administration", async () => {
    const request = vi.spyOn(api, "getFactoryControlOverview").mockResolvedValue(overview);
    const { unmount } = renderRoute(["COMPANY_ADMINISTER"], "/admin/factory-control?lane=OM1-A");
    expect(await screen.findByText(/Showing lane OM1-A/)).toBeVisible();
    expect(request).toHaveBeenCalledWith({ lane: "OM1-A", domain: undefined });
    unmount();
    renderRoute([]);
    expect(screen.getByText("Owner or Company administrator authority is required.")).toBeVisible();
  });

  it("does not invent telemetry when the endpoint is unavailable", async () => {
    vi.spyOn(api, "getFactoryControlOverview").mockRejectedValue(new Error("protected detail"));
    renderRoute();
    expect(await screen.findByText(/No progress or health values were inferred/)).toBeVisible();
    expect(screen.queryByText("protected detail")).not.toBeInTheDocument();
  });
});
