import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { useAuth } from "../auth/useAuth";
import { useEffectivePermissions } from "../auth/usePermissions";
import { useAnalyticsSummary } from "../hooks/useAnalyticsSummary";
import {
  useBeaconLifecycleActions,
  useBeaconSignals,
  useBeaconWorkflowActions,
} from "../hooks/useBeaconSignals";
import { useJobs } from "../hooks/useJobs";
import { CommandCenterRoute } from "./CommandCenterRoute";

vi.mock("../hooks/useAnalyticsSummary");
vi.mock("../hooks/useBeaconSignals");
vi.mock("../hooks/useJobs");
vi.mock("../auth/useAuth");
vi.mock("../auth/usePermissions");

const analyticsHook = vi.mocked(useAnalyticsSummary);
const beaconHook = vi.mocked(useBeaconSignals);
const beaconLifecycleHook = vi.mocked(useBeaconLifecycleActions);
const beaconWorkflowHook = vi.mocked(useBeaconWorkflowActions);
const jobsHook = vi.mocked(useJobs);

describe("CommandCenterRoute", () => {
  it("renders connected metrics without fabricating workforce activity", () => {
    vi.mocked(useAuth).mockReturnValue({ user: { id: "user-a" } } as ReturnType<
      typeof useAuth
    >);
    vi.mocked(useEffectivePermissions).mockReturnValue(new Set([
      "COMPANY_ANALYTICS_READ", "COMPANY_JOB_READ",
    ]));
    beaconWorkflowHook.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: false,
    } as unknown as ReturnType<typeof useBeaconWorkflowActions>);
    beaconLifecycleHook.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: false,
    } as unknown as ReturnType<typeof useBeaconLifecycleActions>);
    beaconHook.mockReturnValue({
      data: {
        items: [],
        snoozed_items: [],
        evaluated_at: "2026-07-24T00:00:00Z",
        expires_at: "2026-07-24T00:15:00Z",
        lifecycle_commands_available: false,
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useBeaconSignals>);
    analyticsHook.mockReturnValue({
      data: {
        period_start: "2026-07-24T00:00:00Z",
        period_end: "2026-07-25T00:00:00Z",
        timezone: "America/New_York",
        cash_collected: { name: "Cash collected", value: "950" },
        booked_revenue: { name: "Booked revenue", value: "1250" },
        new_customers: { name: "New customers", value: 3 },
        appointments_booked: { name: "Appointments", value: 5 },
        total_events: { name: "Events", value: 8 },
        recent_activity: [],
      },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useAnalyticsSummary>);
    jobsHook.mockReturnValue({
      data: { items: [], page: 1, page_size: 1, total_count: 7, total_pages: 7 },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useJobs>);

    render(<MemoryRouter><CommandCenterRoute /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Command Center", level: 2 })).toBeInTheDocument();
    expect(screen.getByText("$1,250")).toBeInTheDocument();
    expect(screen.getByText("No critical issues requiring attention.")).toBeInTheDocument();
    expect(screen.getByText("No active Beacon signals")).toBeInTheDocument();
    expect(screen.getAllByText("Not Connected").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Coming Soon").length).toBeGreaterThan(0);
    expect(screen.queryByText(/Codex.*live/i)).not.toBeInTheDocument();
  });

  it("renders honest unavailable states when connected APIs fail", () => {
    vi.mocked(useAuth).mockReturnValue({ user: { id: "user-a" } } as ReturnType<
      typeof useAuth
    >);
    vi.mocked(useEffectivePermissions).mockReturnValue(new Set([
      "COMPANY_ANALYTICS_READ", "COMPANY_JOB_READ",
    ]));
    beaconWorkflowHook.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: false,
    } as unknown as ReturnType<typeof useBeaconWorkflowActions>);
    beaconLifecycleHook.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: false,
    } as unknown as ReturnType<typeof useBeaconLifecycleActions>);
    beaconHook.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useBeaconSignals>);
    analyticsHook.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as unknown as ReturnType<typeof useAnalyticsSummary>);
    jobsHook.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as unknown as ReturnType<typeof useJobs>);

    render(<MemoryRouter><CommandCenterRoute /></MemoryRouter>);
    expect(screen.getAllByText("No Data Available").length).toBeGreaterThanOrEqual(4);
    expect(screen.queryByText("$0")).not.toBeInTheDocument();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
    expect(screen.getByText("Beacon signals unavailable")).toBeInTheDocument();
  });

  it("does not request cross-domain evidence without its exact read permission", () => {
    vi.mocked(useAuth).mockReturnValue({ user: { id: "user-a" } } as ReturnType<typeof useAuth>);
    vi.mocked(useEffectivePermissions).mockReturnValue(new Set());
    analyticsHook.mockReturnValue({ isLoading: false, isError: false } as ReturnType<typeof useAnalyticsSummary>);
    beaconHook.mockReturnValue({ isLoading: false, isError: false } as ReturnType<typeof useBeaconSignals>);
    jobsHook.mockReturnValue({ isLoading: false, isError: false } as ReturnType<typeof useJobs>);
    beaconWorkflowHook.mockReturnValue({ mutate: vi.fn(), isPending: false, isError: false } as unknown as ReturnType<typeof useBeaconWorkflowActions>);
    beaconLifecycleHook.mockReturnValue({ mutate: vi.fn(), isPending: false, isError: false } as unknown as ReturnType<typeof useBeaconLifecycleActions>);

    render(<MemoryRouter><CommandCenterRoute /></MemoryRouter>);

    expect(analyticsHook).toHaveBeenCalledWith(false);
    expect(beaconHook).toHaveBeenCalledWith(false);
    expect(jobsHook).toHaveBeenCalledWith({ page: 1, pageSize: 1 }, false);
    expect(screen.getByText("Beacon access unavailable")).toBeInTheDocument();
    expect(screen.queryByText("No active Beacon signals")).not.toBeInTheDocument();
  });
});
