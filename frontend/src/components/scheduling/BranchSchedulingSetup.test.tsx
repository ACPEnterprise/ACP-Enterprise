import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as schedulingApi from "../../api/scheduling";
import { BranchSchedulingSetup } from "./BranchSchedulingSetup";

vi.mock("../../auth", () => ({
  useAuth: () => ({
    activeCompany: {
      default_branch_id: "branch-main",
      branches: [{ id: "branch-main", name: "MAIN Branch" }],
    },
  }),
}));

function renderSetup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><BranchSchedulingSetup /></QueryClientProvider>);
}

describe("BranchSchedulingSetup", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("shows exact missing-policy blockers without inventing owner values", async () => {
    vi.spyOn(schedulingApi, "getBranchSchedulingPolicy").mockResolvedValue({
      branch_id: "branch-main", timezone: "America/New_York", status: "NOT_CONFIGURED",
      readiness: "SCHEDULING_SETUP_REQUIRED", blockers: ["NO_ACTIVE_CALENDAR", "NO_OPERATING_HOURS", "CAPACITY_NOT_CONFIGURED"],
      version: null, booking_horizon_days: null, minimum_notice_minutes: null,
      slot_interval_minutes: null, default_capacity_units: null, weekly_intervals: [], exceptions: [],
    });
    renderSetup();
    expect(await screen.findByText("SCHEDULING SETUP REQUIRED")).toBeVisible();
    expect(screen.getByText("No operating hours configured")).toBeVisible();
    expect(screen.getByLabelText("Booking horizon (days)")).toHaveValue(null);
    expect(screen.getByLabelText("Default capacity")).toHaveValue(null);
  });

  it("submits an explicitly entered versioned policy", async () => {
    vi.spyOn(schedulingApi, "getBranchSchedulingPolicy").mockResolvedValue({
      branch_id: "branch-main", timezone: "America/New_York", status: "INACTIVE",
      readiness: "SCHEDULING_SETUP_REQUIRED", blockers: ["NO_ACTIVE_CALENDAR", "NO_OPERATING_HOURS"],
      version: 3, booking_horizon_days: 90, minimum_notice_minutes: 30,
      slot_interval_minutes: 15, default_capacity_units: "2.00", weekly_intervals: [], exceptions: [],
    });
    const configure = vi.spyOn(schedulingApi, "configureBranchSchedulingPolicy").mockImplementation(async (_, input) => ({
      branch_id: "branch-main", timezone: "America/New_York", status: "ACTIVE", readiness: "SCHEDULING_READY", blockers: [], version: 4,
      booking_horizon_days: input.booking_horizon_days, minimum_notice_minutes: input.minimum_notice_minutes,
      slot_interval_minutes: input.slot_interval_minutes, default_capacity_units: input.default_capacity_units,
      weekly_intervals: input.weekly_intervals, exceptions: input.exceptions,
    }));
    renderSetup();
    await screen.findByText("SCHEDULING SETUP REQUIRED");
    fireEvent.click(screen.getByLabelText("Active calendar"));
    fireEvent.click(screen.getByRole("button", { name: "Add interval" }));
    fireEvent.change(screen.getByLabelText("Change reason"), { target: { value: "Owner confirmed hours" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Scheduling Setup" }));
    await screen.findByText("Branch Scheduling setup saved.");
    expect(configure).toHaveBeenCalledWith("branch-main", expect.objectContaining({ expected_version: 3, active: true, reason: "Owner confirmed hours" }));
  });
});
