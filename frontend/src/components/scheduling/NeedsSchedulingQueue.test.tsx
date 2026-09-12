import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import type { DispatchBoardItem } from "../../types/dispatch";
import type { JobListItem } from "../../types/jobs";
import type { AppointmentDetail } from "../../types/scheduling";
import { NeedsSchedulingQueue, type QueueAssignmentFilter, type QueueSort } from "./NeedsSchedulingQueue";

const job = (id: string, overrides: Partial<JobListItem> = {}): JobListItem => ({
  id, job_number: `JOB-${id}`, branch_id: "branch-1", customer_id: `customer-${id}`,
  customer_display_name: `Customer ${id}`, service_location_id: `location-${id}`,
  service_location_label: `${id} Main Street`, status: "ready", priority: "normal",
  job_type_code: "service", customer_reported_problem_summary: null, appointment_count: 0,
  earliest_appointment_start_at: null, created_at: "2026-09-01T12:00:00Z",
  updated_at: "2026-09-01T12:00:00Z", started_at: null, completed_at: null,
  concurrency_version: 1, ...overrides,
});
const appointment = (id: string, overrides: Partial<AppointmentDetail> = {}): AppointmentDetail => ({
  id, appointment_number: `APT-${id}`, company_id: "company-1", branch_id: "branch-1",
  customer_id: `customer-${id}`, service_location_id: `location-${id}`, status: "scheduled",
  arrival_window_start_at: "2026-09-15T13:00:00Z", arrival_window_end_at: "2026-09-15T16:00:00Z",
  expected_duration_minutes: 90, capacity_units: "1.00", concurrency_version: 1,
  reschedule_count: 0, rescheduled_at: null, cancelled_at: null, cancellation_reason_code: null,
  created_at: "2026-09-02T12:00:00Z", updated_at: "2026-09-02T12:00:00Z", ...overrides,
});
const dispatch = (appointmentId: string, jobId: string, assigned = false): DispatchBoardItem => ({
  appointment_id: appointmentId, appointment_number: `APT-${appointmentId}`, job_id: jobId,
  branch_id: "branch-1", status: "scheduled", window_start_at: "2026-09-15T13:00:00Z",
  window_end_at: "2026-09-15T16:00:00Z", assignment: assigned ? {
    id: `assignment-${appointmentId}`, appointment_id: appointmentId, appointment_number: `APT-${appointmentId}`,
    job_id: jobId, company_id: "company-1", branch_id: "branch-1", primary_employee_id: "employee-1",
    primary_employee_name: "Casey Technician", status: "assigned", arrival_state: "pending",
    active_exception_code: null, assignment_reason: "human_dispatch", window_start_at: "2026-09-15T13:00:00Z",
    window_end_at: "2026-09-15T16:00:00Z", effective_at: "2026-09-02T12:00:00Z",
    released_at: null, version: 1, crew_members: [],
  } : null,
});

function renderQueue(options: { assignment?: QueueAssignmentFilter; sort?: QueueSort; status?: "" | "ready"; priority?: "" | "emergency"; search?: string } = {}) {
  const jobs = [
    job("emergency", { priority: "emergency", created_at: "2026-08-30T12:00:00Z" }),
    job("unassigned", { earliest_appointment_start_at: "2026-09-15T13:00:00Z", appointment_count: 1 }),
    job("assigned", { earliest_appointment_start_at: "2026-09-15T14:00:00Z", appointment_count: 1 }),
  ];
  const appointments = [appointment("unassigned"), appointment("assigned"), appointment("partial")];
  const dispatches = [dispatch("unassigned", "unassigned"), dispatch("assigned", "assigned", true)];
  const onSelect = vi.fn();
  render(<MemoryRouter><NeedsSchedulingQueue
    jobs={jobs} appointments={appointments}
    dispatchByAppointment={new Map(dispatches.map((item) => [item.appointment_id, item]))}
    jobsById={new Map(jobs.map((item) => [item.id, item]))}
    branches={[{ id: "branch-1", name: "Main Branch" }]} search={options.search ?? ""}
    jobStatus={options.status ?? ""} priority={options.priority ?? ""}
    assignmentFilter={options.assignment ?? "needs_attention"} sort={options.sort ?? "oldest"}
    returnTo="/scheduling?view=unassigned&branch=branch-1"
    onJobStatusChange={vi.fn()} onPriorityChange={vi.fn()} onAssignmentFilterChange={vi.fn()}
    onSortChange={vi.fn()} onSelect={onSelect}
  /></MemoryRouter>);
  return { onSelect };
}

describe("NeedsSchedulingQueue", () => {
  it("shows unscheduled, scheduled-unassigned, emergency, and partial truth without assigned noise", () => {
    renderQueue();
    const queue = screen.getByRole("article", { name: "Needs scheduling work queue" });
    expect(within(queue).getAllByText("NEEDS_SCHEDULING")).toHaveLength(1);
    expect(within(queue).getAllByText("SCHEDULED_UNASSIGNED")).toHaveLength(2);
    expect(within(queue).getByText("EMERGENCY")).toBeVisible();
    expect(within(queue).getByText("PARTIAL")).toBeVisible();
    expect(within(queue).queryByText("Casey Technician")).not.toBeInTheDocument();
    expect(within(queue).getByText("Not established")).toBeVisible();
  });

  it("exposes assigned comparison and selects only through explicit human action", async () => {
    const { onSelect } = renderQueue({ assignment: "assigned" });
    expect(screen.getByText("Casey Technician")).toBeVisible();
    expect(screen.queryByText("JOB-emergency")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Inspect assignment" }));
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: "assigned" }));
  });

  it("preserves queue context in Customer, Location, Job, and Appointment links", () => {
    renderQueue();
    expect(screen.getAllByRole("link", { name: "Open Job to schedule" })[0]).toHaveAttribute("href", expect.stringContaining("returnTo=%2Fscheduling%3Fview%3Dunassigned%26branch%3Dbranch-1"));
    expect(screen.getAllByRole("link", { name: "Open Location" })[0]).toHaveAttribute("href", expect.stringMatching(/returnTo=.*#service-location-/));
    expect(screen.getAllByRole("link", { name: "Open Customer" })[0]).toHaveAttribute("href", expect.stringContaining("returnTo="));
    expect(screen.getAllByRole("link", { name: "Open Appointment" })[0]).toHaveAttribute("href", expect.stringContaining("returnTo="));
  });

  it("applies authoritative Job priority and search filters and shows a truthful empty state", () => {
    renderQueue({ priority: "emergency", search: "does-not-match" });
    expect(screen.getByText(/No work matches this authorized queue scope/)).toBeVisible();
    expect(screen.queryByText("JOB-emergency")).not.toBeInTheDocument();
  });
});
