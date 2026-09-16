import type { DispatchBoardItem } from "../../types/dispatch";
import type { JobListItem } from "../../types/jobs";
import type { AppointmentDetail } from "../../types/scheduling";

export const CURRENT_CALENDAR_SOURCE_BASELINE = {
  contract: "hcp-source4-realworld-acceptance-snapshot/v1",
  asOf: "2026-09-12",
  customers: 11,
  locations: 11,
  jobs: 15,
  appointments: 18,
  currentFutureAppointments: 14,
} as const;

export const CURRENT_CALENDAR_QUERY_RANGE = {
  startAt: "2026-09-12T04:00:00.000Z",
  endAt: "2026-12-14T04:00:00.000Z",
} as const;

export type CalendarReadinessState = "READY" | "INCOMPLETE" | "PARTIAL";

export interface CalendarGraphReadiness {
  readonly state: CalendarReadinessState;
  readonly customers: number;
  readonly locations: number;
  readonly jobs: number;
  readonly currentFutureAppointments: number;
  readonly missing: readonly string[];
}

export function buildCalendarGraphReadiness(
  appointments: readonly AppointmentDetail[],
  jobs: readonly JobListItem[],
  complete: boolean,
): CalendarGraphReadiness {
  const customers = new Set(jobs.map((job) => job.customer_id).filter(Boolean))
    .size;
  const locations = new Set(
    jobs.map((job) => job.service_location_id).filter(Boolean),
  ).size;
  const observed = {
    customers,
    locations,
    jobs: jobs.length,
    currentFutureAppointments: appointments.length,
  };
  const expected = CURRENT_CALENDAR_SOURCE_BASELINE;
  const missing = (
    ["customers", "locations", "jobs", "currentFutureAppointments"] as const
  )
    .filter((key) => observed[key] < expected[key])
    .map((key) => `${key}:${expected[key] - observed[key]}`);
  const excess = (
    ["customers", "locations", "jobs", "currentFutureAppointments"] as const
  )
    .filter((key) => observed[key] > expected[key])
    .map((key) => `${key}:unexpected_${observed[key] - expected[key]}`);
  return {
    state: !complete
      ? "PARTIAL"
      : missing.length || excess.length
        ? "INCOMPLETE"
        : "READY",
    ...observed,
    missing: [...missing, ...excess],
  };
}

export interface CalendarIssue {
  readonly key: string;
  readonly kind:
    "INVALID_WINDOW" | "OVERLAP" | "MISSING_JOB" | "MISSING_LOCATION";
  readonly message: string;
}

const activeTechnician = (item?: DispatchBoardItem) =>
  item?.assignment &&
  !["released", "replaced", "cancelled"].includes(item.assignment.status)
    ? item.assignment.primary_employee_id
    : null;

export function calendarIssues(
  appointments: readonly AppointmentDetail[],
  dispatchByAppointment: ReadonlyMap<string, DispatchBoardItem>,
  jobsById: ReadonlyMap<string, JobListItem>,
): readonly CalendarIssue[] {
  const issues: CalendarIssue[] = [];
  const valid: Array<{
    appointment: AppointmentDetail;
    start: number;
    end: number;
    technician: string;
  }> = [];
  for (const appointment of appointments) {
    const start = appointment.arrival_window_start_at
      ? Date.parse(appointment.arrival_window_start_at)
      : Number.NaN;
    const end = appointment.arrival_window_end_at
      ? Date.parse(appointment.arrival_window_end_at)
      : Number.NaN;
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) {
      issues.push({
        key: `window:${appointment.id}`,
        kind: "INVALID_WINDOW",
        message: `${appointment.appointment_number} has an incomplete or invalid arrival window.`,
      });
    }
    const dispatch = dispatchByAppointment.get(appointment.id);
    const job = dispatch?.job_id ? jobsById.get(dispatch.job_id) : undefined;
    if (!job)
      issues.push({
        key: `job:${appointment.id}`,
        kind: "MISSING_JOB",
        message: `${appointment.appointment_number} is missing its authorized Job projection.`,
      });
    else if (!job.service_location_id)
      issues.push({
        key: `location:${appointment.id}`,
        kind: "MISSING_LOCATION",
        message: `${job.job_number} is missing its Service Location projection.`,
      });
    const technician = activeTechnician(dispatch);
    if (
      technician &&
      Number.isFinite(start) &&
      Number.isFinite(end) &&
      end > start
    )
      valid.push({ appointment, start, end, technician });
  }
  valid.sort(
    (left, right) =>
      left.start - right.start ||
      left.appointment.appointment_number.localeCompare(
        right.appointment.appointment_number,
      ),
  );
  for (let index = 0; index < valid.length; index += 1) {
    for (
      let next = index + 1;
      next < valid.length && valid[next].start < valid[index].end;
      next += 1
    ) {
      if (valid[index].technician === valid[next].technician) {
        issues.push({
          key: `overlap:${valid[index].appointment.id}:${valid[next].appointment.id}`,
          kind: "OVERLAP",
          message: `${valid[index].appointment.appointment_number} overlaps ${valid[next].appointment.appointment_number} for the same technician.`,
        });
      }
    }
  }
  return issues;
}

export function sortAppointments(
  items: readonly AppointmentDetail[],
): readonly AppointmentDetail[] {
  return [...items].sort((left, right) => {
    const leftStart = left.arrival_window_start_at
      ? Date.parse(left.arrival_window_start_at)
      : Number.POSITIVE_INFINITY;
    const rightStart = right.arrival_window_start_at
      ? Date.parse(right.arrival_window_start_at)
      : Number.POSITIVE_INFINITY;
    return (
      leftStart - rightStart ||
      left.appointment_number.localeCompare(right.appointment_number)
    );
  });
}
