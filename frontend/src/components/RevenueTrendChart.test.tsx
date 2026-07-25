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
});
