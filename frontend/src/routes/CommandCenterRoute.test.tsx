import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { useAnalyticsSummary } from "../hooks/useAnalyticsSummary";
import { useJobs } from "../hooks/useJobs";
import { CommandCenterRoute } from "./CommandCenterRoute";

vi.mock("../hooks/useAnalyticsSummary");
vi.mock("../hooks/useJobs");

const analyticsHook = vi.mocked(useAnalyticsSummary);
const jobsHook = vi.mocked(useJobs);

describe("CommandCenterRoute", () => {
  it("renders connected metrics without fabricating workforce activity", () => {
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
    expect(screen.getAllByText("Not Connected").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Coming Soon").length).toBeGreaterThan(0);
    expect(screen.queryByText(/Codex.*live/i)).not.toBeInTheDocument();
  });

  it("renders honest unavailable states when connected APIs fail", () => {
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
  });
});
