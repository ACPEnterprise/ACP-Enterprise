import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as analyticsHook from "../hooks/useAnalyticsSummary";
import { MissionControlRoute } from "./MissionControlRoute";

vi.mock("../hooks/useAnalyticsSummary");
const permissions = new Set<string>();
vi.mock("../auth", () => ({
  useHasPermission: (code: string) => permissions.has(code),
}));
vi.mock("../components/RevenueTrendChart", () => ({
  RevenueTrendChart: () => <div>Authoritative revenue trend</div>,
}));

const data = {
  cash_collected: { name: "Cash Collected", value: "1250", event_count: 2 },
  booked_revenue: { name: "Booked Revenue", value: "2300", event_count: 3 },
  new_customers: { name: "New Customers", value: 4 },
  appointments_booked: { name: "Appointments Booked", value: 5 },
  total_events: { name: "Total Events", value: 14 },
  recent_activity: [],
};

describe("MissionControlRoute", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    permissions.clear();
    permissions.add("COMPANY_ANALYTICS_READ");
  });

  it("renders a truthful loading state", () => {
    vi.mocked(analyticsHook.useAnalyticsSummary).mockReturnValue({
      isLoading: true,
      isError: false,
      dataUpdatedAt: 0,
    } as never);
    render(<MissionControlRoute />);
    expect(screen.getByRole("status", { name: "Loading analytics" })).toBeInTheDocument();
    expect(screen.getByText("Checking analytics API")).toBeInTheDocument();
  });

  it("renders API failure without claiming complete system health", () => {
    vi.mocked(analyticsHook.useAnalyticsSummary).mockReturnValue({
      isLoading: false,
      isError: true,
      error: new Error("sql://protected-analytics-canary"),
      dataUpdatedAt: 0,
    } as never);
    render(<MissionControlRoute />);
    expect(screen.getByText("Analytics API unavailable")).toBeInTheDocument();
    expect(screen.queryByText("System Online")).not.toBeInTheDocument();
    expect(screen.queryByText(/protected-analytics-canary/)).not.toBeInTheDocument();
  });

  it("uses only authoritative metrics and an honest empty activity state", () => {
    vi.mocked(analyticsHook.useAnalyticsSummary).mockReturnValue({
      isLoading: false,
      isError: false,
      data,
      dataUpdatedAt: Date.now(),
    } as never);
    render(<MissionControlRoute />);
    expect(screen.getByText("Analytics API available")).toBeInTheDocument();
    expect(screen.getByText("No recent authoritative activity is available.")).toBeInTheDocument();
    expect(screen.queryByText("Today's Revenue Goal")).not.toBeInTheDocument();
    expect(screen.queryByText("Top Technicians")).not.toBeInTheDocument();
    expect(screen.queryByText("Mike")).not.toBeInTheDocument();
  });

  it("does not request Analytics without exact read authority", () => {
    permissions.clear();
    vi.mocked(analyticsHook.useAnalyticsSummary).mockReturnValue({
      isLoading: false, isError: false, dataUpdatedAt: 0,
    } as never);

    render(<MissionControlRoute />);

    expect(analyticsHook.useAnalyticsSummary).toHaveBeenCalledWith(false);
    expect(screen.getByText(/not authorized to view Mission Control/i)).toBeInTheDocument();
    expect(screen.queryByText("Analytics API available")).not.toBeInTheDocument();
  });
});
