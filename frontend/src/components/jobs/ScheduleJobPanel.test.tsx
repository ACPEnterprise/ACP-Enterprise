import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useScheduleExistingJob } from "../../hooks/useOperations";
import { useWorkforceDirectory } from "../../hooks/useWorkforce";
import type { JobDetail } from "../../types/jobs";
import { ScheduleJobPanel } from "./ScheduleJobPanel";

vi.mock("../../hooks/useOperations");
vi.mock("../../hooks/useWorkforce");

const mutate = vi.fn();
const job = {
  id: "job-1", job_number: "JOB-000306", branch_id: "branch-main",
  status: "in_progress", concurrency_version: 3,
  customer: { id: "customer-1", display_name: "Synthetic Acceptance", customer_number: "CUS-002070" },
  service_location: { id: "location-1" }, appointments: [],
} as unknown as JobDetail;

function renderPanel(canAssign = true) {
  return render(<QueryClientProvider client={new QueryClient()}><ScheduleJobPanel job={job} canAssign={canAssign} /></QueryClientProvider>);
}

describe("ScheduleJobPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useScheduleExistingJob).mockReturnValue({ mutate, isPending: false, isSuccess: false, error: null } as never);
    vi.mocked(useWorkforceDirectory).mockReturnValue({ isLoading: false, data: [
      { employee_id: "employee-beta", employee_number: "SYN-BETA", display_name: "Synthetic Beta Employee", employee_status: "active", technician: true, home_branch_id: "branch-main" },
      { employee_id: "employee-other", employee_number: "OTHER", display_name: "Other Branch", employee_status: "active", technician: true, home_branch_id: "branch-other" },
    ] } as never);
  });

  it("offers human-readable assignment or explicit Unassigned and keeps Job identities", async () => {
    renderPanel();
    expect(screen.getByRole("heading", { name: "Schedule Job" })).toBeVisible();
    expect(screen.getByRole("option", { name: "Unassigned / Needs Scheduling" })).toBeVisible();
    expect(screen.getByRole("option", { name: "Synthetic Beta Employee — SYN-BETA" })).toBeVisible();
    expect(screen.queryByRole("option", { name: /Other Branch/ })).not.toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText(/^Arrival window starts/));
    await userEvent.type(screen.getByLabelText(/^Arrival window starts/), "2026-09-14T09:00");
    await userEvent.clear(screen.getByLabelText(/^Arrival window ends/));
    await userEvent.type(screen.getByLabelText(/^Arrival window ends/), "2026-09-14T12:00");
    await userEvent.clear(screen.getByLabelText(/^Expected duration \(minutes\)/));
    await userEvent.type(screen.getByLabelText(/^Expected duration \(minutes\)/), "90");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Technician" }), "employee-beta");
    await userEvent.click(screen.getByRole("button", { name: "Book Appointment" }));
    expect(mutate).toHaveBeenCalledWith(expect.objectContaining({
      expected_job_version: 3,
      branch_id: "branch-main",
      customer_id: "customer-1",
      service_location_id: "location-1",
      arrival_window_start_at: new Date("2026-09-14T09:00").toISOString(),
      arrival_window_end_at: new Date("2026-09-14T12:00").toISOString(),
      expected_duration_minutes: 90,
      employee_id: "employee-beta",
      reserve_capacity: true,
    }), expect.any(Object));
  });

  it("rejects an inverted arrival window without changing work duration semantics", async () => {
    renderPanel();
    await userEvent.clear(screen.getByLabelText(/^Arrival window starts/));
    await userEvent.type(screen.getByLabelText(/^Arrival window starts/), "2026-09-14T12:00");
    await userEvent.clear(screen.getByLabelText(/^Arrival window ends/));
    await userEvent.type(screen.getByLabelText(/^Arrival window ends/), "2026-09-14T09:00");
    expect(screen.getByText("Arrival window must end after it starts.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Book Appointment" })).toBeDisabled();
    expect(mutate).not.toHaveBeenCalled();
  });

  it("books Needs Scheduling without claiming technician capacity", async () => {
    renderPanel();
    await userEvent.click(screen.getByRole("button", { name: "Book Appointment" }));
    expect(mutate).toHaveBeenCalledWith(expect.objectContaining({
      employee_id: null,
      reserve_capacity: false,
    }), expect.any(Object));
  });

  it("explains emergency work and permits scheduling without Dispatch authority", () => {
    renderPanel(false);
    expect(screen.getByText(/supports emergency work before scheduling/i)).toBeVisible();
    expect(screen.getByRole("combobox", { name: "Technician" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Book Appointment" })).toBeEnabled();
  });
});
