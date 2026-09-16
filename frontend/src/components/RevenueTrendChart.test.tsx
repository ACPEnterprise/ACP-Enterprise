import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as revenueHook from "../hooks/useRevenueTrend";
import { RevenueTrendChart } from "./RevenueTrendChart";

vi.mock("../hooks/useRevenueTrend");

describe("RevenueTrendChart", () => {
  beforeEach(() => vi.resetAllMocks());

  it("renders truthful loading, failure, and empty states", () => {
    vi.mocked(revenueHook.useRevenueTrend).mockReturnValueOnce({
      isLoading: true,
    } as never);
    const view = render(<RevenueTrendChart />);
    expect(screen.getByText("Loading revenue trend…")).toBeInTheDocument();

    vi.mocked(revenueHook.useRevenueTrend).mockReturnValueOnce({
      isLoading: false,
      isError: true,
    } as never);
    view.rerender(<RevenueTrendChart />);
    expect(screen.getByText("Unable to load revenue trend.")).toBeInTheDocument();

    vi.mocked(revenueHook.useRevenueTrend).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { points: [] },
    } as never);
    view.rerender(<RevenueTrendChart />);
    expect(
      screen.getByText("No revenue trend data is available."),
    ).toBeInTheDocument();
  });

  it("labels period authority and invalid-evidence gaps", () => {
    vi.mocked(revenueHook.useRevenueTrend).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        period_start: "2026-09-10T04:00:00Z",
        period_end: "2026-09-17T03:59:59Z",
        timezone: "America/New_York",
        days: 7,
        authority: "business_event_projection",
        completeness: "PARTIAL",
        excluded_event_count: 1,
        points: [{
          date: "2026-09-10",
          booked_revenue: "20.00",
          cash_collected: null,
          booked_event_count: 1,
          payment_event_count: 0,
          excluded_booked_event_count: 0,
          excluded_payment_event_count: 1,
        }],
      },
    } as never);
    render(<RevenueTrendChart />);
    expect(screen.getByText(/America\/New_York · PARTIAL evidence/)).toBeInTheDocument();
    expect(screen.getByText(/1 monetary event\(s\) excluded/)).toBeInTheDocument();
  });
});
