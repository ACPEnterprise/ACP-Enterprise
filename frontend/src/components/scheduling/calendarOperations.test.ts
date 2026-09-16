import { describe, expect, it } from "vitest";

import type { DispatchBoardItem } from "../../types/dispatch";
import type { JobListItem } from "../../types/jobs";
import type { AppointmentDetail } from "../../types/scheduling";
import {
  buildCalendarGraphReadiness,
  calendarIssues,
  sortAppointments,
} from "./calendarOperations";

const appointment = (
  id: string,
  start = "2026-09-15T13:00:00Z",
  end = "2026-09-15T14:00:00Z",
) =>
  ({
    id,
    appointment_number: `APT-${id}`,
    arrival_window_start_at: start,
    arrival_window_end_at: end,
  }) as AppointmentDetail;
const job = (id: string) =>
  ({
    id,
    job_number: `JOB-${id}`,
    customer_id: `customer-${id}`,
    service_location_id: `location-${id}`,
  }) as JobListItem;
const dispatch = (id: string, employee = "employee-1") =>
  ({
    appointment_id: id,
    job_id: id,
    assignment: { status: "assigned", primary_employee_id: employee },
  }) as DispatchBoardItem;

describe("calendar operations", () => {
  it("sorts dense appointment input deterministically by authoritative start then number", () => {
    expect(
      sortAppointments([
        appointment("2", "2026-09-15T14:00:00Z", "2026-09-15T15:00:00Z"),
        appointment("1"),
      ]).map((item) => item.id),
    ).toEqual(["1", "2"]);
  });

  it("reports invalid windows, missing graph context, and same-technician overlap", () => {
    const appointments = [
      appointment("1"),
      appointment("2", "2026-09-15T13:30:00Z", "2026-09-15T14:30:00Z"),
      appointment("3", null as unknown as string, null as unknown as string),
    ];
    const jobs = new Map([
      ["1", job("1")],
      ["2", job("2")],
    ]);
    const dispatches = new Map([
      ["1", dispatch("1")],
      ["2", dispatch("2")],
    ]);
    expect(
      calendarIssues(appointments, dispatches, jobs).map((item) => item.kind),
    ).toEqual(
      expect.arrayContaining(["OVERLAP", "INVALID_WINDOW", "MISSING_JOB"]),
    );
  });

  it("fails closed when the native graph query is partial", () => {
    expect(buildCalendarGraphReadiness([], [], false)).toMatchObject({
      state: "PARTIAL",
      customers: 0,
      jobs: 0,
    });
  });
});
