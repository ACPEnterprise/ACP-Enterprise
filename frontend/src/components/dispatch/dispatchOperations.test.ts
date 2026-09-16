import { describe, expect, it, vi } from "vitest";
import type { DispatchBoardItem } from "../../types/dispatch";
import type { JobListItem } from "../../types/jobs";
import {
  filterDispatchBoard,
  operationalState,
  technicianLoads,
} from "./dispatchOperations";

const item = (
  id: string,
  start: string,
  end: string,
  name: string | null = "Tech One",
) =>
  ({
    appointment_id: id,
    appointment_number: `APT-${id}`,
    job_id: id,
    branch_id: "main",
    status: "scheduled",
    window_start_at: start,
    window_end_at: end,
    assignment: name
      ? {
          primary_employee_name: name,
          arrival_state: "pending",
          active_exception_code: null,
          crew_members: [],
          status: "assigned",
        }
      : null,
  }) as DispatchBoardItem;
const jobs = new Map([
  [
    "1",
    {
      id: "1",
      job_number: "JOB-1",
      customer_display_name: "Taylor Home",
      service_location_label: "10 Main Street",
      status: "ready",
    } as JobListItem,
  ],
]);

describe("dispatch operations", () => {
  it("derives existing lifecycle without creating another state machine", () => {
    expect(
      operationalState(
        item("1", "2026-09-15T13:00:00Z", "2026-09-15T14:00:00Z"),
        { status: "in_progress" } as JobListItem,
      ),
    ).toBe("STARTED");
  });
  it("filters by Customer/location and unassigned truth", () => {
    const assigned = item("1", "2026-09-15T13:00:00Z", "2026-09-15T14:00:00Z");
    const unassigned = item(
      "2",
      "2026-09-15T14:00:00Z",
      "2026-09-15T15:00:00Z",
      null,
    );
    expect(
      filterDispatchBoard([assigned, unassigned], jobs, "all", "Taylor", ""),
    ).toEqual([assigned]);
    expect(
      filterDispatchBoard([assigned, unassigned], jobs, "unassigned", "", ""),
    ).toEqual([unassigned]);
  });
  it("summarizes bounded load and overlapping work without claiming availability", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-15T12:00:00Z"));
    const loads = technicianLoads(
      [
        item("1", "2026-09-15T13:00:00Z", "2026-09-15T15:00:00Z"),
        item("2", "2026-09-15T14:00:00Z", "2026-09-15T16:00:00Z"),
      ],
      jobs,
    );
    expect(loads[0]).toMatchObject({
      name: "Tech One",
      appointments: 2,
      minutes: 240,
      overlaps: 1,
      nextJob: "JOB-1",
    });
    vi.useRealTimers();
  });
});
