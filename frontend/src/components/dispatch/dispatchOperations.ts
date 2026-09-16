import type {
  DispatchAssignment,
  DispatchBoardItem,
} from "../../types/dispatch";
import type { JobListItem } from "../../types/jobs";

export type DispatchBoardFilter =
  "all" | "unassigned" | "active" | "exception" | "completed";

export function activeDispatchAssignment(
  item: DispatchBoardItem,
): DispatchAssignment | null {
  const assignment = item.assignment;
  return assignment &&
    !["released", "replaced", "cancelled"].includes(assignment.status)
    ? assignment
    : null;
}

export function operationalState(
  item: DispatchBoardItem,
  job?: JobListItem,
): string {
  const assignment = activeDispatchAssignment(item);
  if (item.status === "cancelled" || job?.status === "cancelled")
    return "CANCELED";
  if (item.status === "completed" || job?.status === "completed")
    return "COMPLETED";
  if (job?.status === "in_progress") return "STARTED";
  if (job?.status === "paused") return "PAUSED";
  if (assignment?.arrival_state === "arrived") return "ARRIVED";
  if (assignment?.arrival_state === "en_route") return "ON_MY_WAY";
  return assignment ? "ASSIGNED" : "UNASSIGNED";
}

export function filterDispatchBoard(
  items: readonly DispatchBoardItem[],
  jobsById: ReadonlyMap<string, JobListItem>,
  filter: DispatchBoardFilter,
  search: string,
  technician: string,
): readonly DispatchBoardItem[] {
  const needle = search.trim().toLowerCase();
  return items.filter((item) => {
    const assignment = activeDispatchAssignment(item);
    const job = item.job_id ? jobsById.get(item.job_id) : undefined;
    const state = operationalState(item, job);
    const assignedNames = [
      assignment?.primary_employee_name,
      ...(assignment?.crew_members ?? []).map((member) => member.display_name),
    ].filter(Boolean) as string[];
    const matchesFilter =
      filter === "all" ||
      (filter === "unassigned" && !assignment) ||
      (filter === "active" &&
        ["ON_MY_WAY", "ARRIVED", "STARTED", "PAUSED"].includes(state)) ||
      (filter === "exception" && Boolean(assignment?.active_exception_code)) ||
      (filter === "completed" && state === "COMPLETED");
    const matchesTechnician = !technician || assignedNames.includes(technician);
    const haystack =
      `${item.appointment_number} ${job?.job_number ?? ""} ${job?.customer_display_name ?? ""} ${job?.service_location_label ?? ""} ${assignedNames.join(" ")} ${state}`.toLowerCase();
    return (
      matchesFilter &&
      matchesTechnician &&
      (!needle || haystack.includes(needle))
    );
  });
}

export interface TechnicianLoad {
  readonly name: string;
  readonly appointments: number;
  readonly minutes: number;
  readonly overlaps: number;
  readonly nextJob: string | null;
  readonly nextLocation: string | null;
}

export function technicianLoads(
  items: readonly DispatchBoardItem[],
  jobsById: ReadonlyMap<string, JobListItem>,
): readonly TechnicianLoad[] {
  const byName = new Map<
    string,
    Array<{ item: DispatchBoardItem; start: number; end: number }>
  >();
  for (const item of items) {
    const assignment = activeDispatchAssignment(item);
    const names = [
      assignment?.primary_employee_name,
      ...(assignment?.crew_members ?? []).map((member) => member.display_name),
    ].filter(Boolean) as string[];
    const start = Date.parse(item.window_start_at);
    const end = Date.parse(item.window_end_at);
    for (const name of names)
      byName.set(name, [...(byName.get(name) ?? []), { item, start, end }]);
  }
  return [...byName.entries()]
    .map(([name, rows]) => {
      rows.sort(
        (left, right) =>
          left.start - right.start ||
          left.item.appointment_number.localeCompare(
            right.item.appointment_number,
          ),
      );
      let overlaps = 0;
      let latestPriorEnd = rows[0]?.end ?? Number.NEGATIVE_INFINITY;
      for (let index = 1; index < rows.length; index += 1) {
        if (rows[index].start < latestPriorEnd) overlaps += 1;
        latestPriorEnd = Math.max(latestPriorEnd, rows[index].end);
      }
      const next = rows.find((row) => row.end >= Date.now()) ?? rows[0];
      const job = next?.item.job_id
        ? jobsById.get(next.item.job_id)
        : undefined;
      return {
        name,
        appointments: rows.length,
        minutes: rows.reduce(
          (total, row) => total + Math.max(0, row.end - row.start) / 60_000,
          0,
        ),
        overlaps,
        nextJob: job?.job_number ?? next?.item.appointment_number ?? null,
        nextLocation: job?.service_location_label ?? null,
      };
    })
    .sort(
      (left, right) =>
        right.overlaps - left.overlaps ||
        right.minutes - left.minutes ||
        left.name.localeCompare(right.name),
    );
}
