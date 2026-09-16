import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useScheduleExistingJob } from "../../hooks/useOperations";
import type { JobDetail } from "../../types/jobs";
import { ScheduleJobPanel } from "./ScheduleJobPanel";

vi.mock("../../hooks/useOperations");

const mutate = vi.fn();
const job = {
  id: "job-1", job_number: "JOB-000306", branch_id: "branch-main",
  status: "in_progress", concurrency_version: 3,
  customer: { id: "customer-1", display_name: "Synthetic Acceptance", customer_number: "CUS-002070" },
  service_location: { id: "location-1" }, appointments: [],
} as unknown as JobDetail;

function renderPanel() {
  return render(<QueryClientProvider client={new QueryClient()}><ScheduleJobPanel job={job} timeZone="America/New_York" /></QueryClientProvider>);
}

describe("ScheduleJobPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useScheduleExistingJob).mockReturnValue({ mutate, isPending: false, isSuccess: false, error: null } as never);
  });

  it("creates the Appointment first and routes technician choice through Dispatch eligibility", async () => {
    renderPanel();
    expect(screen.getByRole("heading", { name: "Schedule Job" })).toBeVisible();
    expect(screen.queryByRole("combobox", { name: "Technician" })).not.toBeInTheDocument();
    expect(screen.getByText(/appointment-specific Branch, capability, availability, and conflict evidence/i)).toBeVisible();
    await userEvent.clear(screen.getByLabelText(/^Arrival window starts/));
    await userEvent.type(screen.getByLabelText(/^Arrival window starts/), "2026-09-14T09:00");
    await userEvent.clear(screen.getByLabelText(/^Arrival window ends/));
    await userEvent.type(screen.getByLabelText(/^Arrival window ends/), "2026-09-14T12:00");
    await userEvent.clear(screen.getByLabelText(/^Expected duration \(minutes\)/));
    await userEvent.type(screen.getByLabelText(/^Expected duration \(minutes\)/), "90");
    await userEvent.click(screen.getByRole("button", { name: "Book Appointment" }));
    expect(mutate).toHaveBeenCalledWith(expect.objectContaining({
      expected_job_version: 3,
      branch_id: "branch-main",
      customer_id: "customer-1",
      service_location_id: "location-1",
      arrival_window_start_at: "2026-09-14T13:00:00.000Z",
      arrival_window_end_at: "2026-09-14T16:00:00.000Z",
      expected_duration_minutes: 90,
      reserve_capacity: false,
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
      reserve_capacity: false,
    }), expect.any(Object));
  });

  it("explains emergency work and permits scheduling before Dispatch assignment", () => {
    renderPanel();
    expect(screen.getByText(/supports emergency work before scheduling/i)).toBeVisible();
    expect(screen.getByRole("button", { name: "Book Appointment" })).toBeEnabled();
  });

  it("preserves the request identity for an exact retry after an uncertain outcome", async () => {
    vi.mocked(useScheduleExistingJob).mockReturnValue({
      mutate,
      isPending: false,
      isSuccess: false,
      error: { isAxiosError: true },
    } as never);
    renderPanel();
    await userEvent.click(screen.getByRole("button", { name: "Book Appointment" }));
    await userEvent.click(screen.getByRole("button", { name: "Retry same request" }));
    expect(screen.getByText(/UNKNOWN REQUIRES REFRESH/)).toBeVisible();
    const first = mutate.mock.calls[0][0];
    const replay = mutate.mock.calls[1][0];
    expect(replay.request_id).toBe(first.request_id);
    expect(replay).toEqual(first);
  });

  it("requires review rather than stale-version replay", () => {
    vi.mocked(useScheduleExistingJob).mockReturnValue({
      mutate,
      isPending: false,
      isSuccess: false,
      error: { isAxiosError: true, response: { status: 409, data: { detail: { code: "stale_version", recovery: "RETRY_AFTER_REFRESH" } } } },
    } as never);
    renderPanel();
    expect(screen.getByText(/FAILED REQUIRES REFRESH/)).toBeVisible();
    expect(screen.getByText(/record changed after it was loaded/i)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Retry same request" })).not.toBeInTheDocument();
  });
});
