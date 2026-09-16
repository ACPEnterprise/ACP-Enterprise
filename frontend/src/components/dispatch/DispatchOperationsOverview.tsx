import type { DispatchBoardItem } from "../../types/dispatch";
import type { JobListItem } from "../../types/jobs";
import { Alert, Badge, Card, Input, Select } from "../../ui";
import {
  operationalState,
  technicianLoads,
  type DispatchBoardFilter,
} from "./dispatchOperations";

export function DispatchOperationsOverview({
  items,
  jobsById,
  filter,
  search,
  technician,
  onFilterChange,
  onSearchChange,
  onTechnicianChange,
}: {
  readonly items: readonly DispatchBoardItem[];
  readonly jobsById: ReadonlyMap<string, JobListItem>;
  readonly filter: DispatchBoardFilter;
  readonly search: string;
  readonly technician: string;
  readonly onFilterChange: (value: DispatchBoardFilter) => void;
  readonly onSearchChange: (value: string) => void;
  readonly onTechnicianChange: (value: string) => void;
}) {
  const technicians = Array.from(
    new Set(
      items
        .flatMap((item) => [
          item.assignment?.primary_employee_name,
          ...(item.assignment?.crew_members ?? []).map(
            (member) => member.display_name,
          ),
        ])
        .filter((name): name is string => Boolean(name)),
    ),
  ).sort();
  const loads = technicianLoads(items, jobsById);
  const states = items.map((item) =>
    operationalState(item, item.job_id ? jobsById.get(item.job_id) : undefined),
  );
  const values = [
    ["Unassigned", states.filter((state) => state === "UNASSIGNED").length],
    [
      "Active work",
      states.filter((state) =>
        ["ON_MY_WAY", "ARRIVED", "STARTED", "PAUSED"].includes(state),
      ).length,
    ],
    [
      "Exceptions",
      items.filter((item) => item.assignment?.active_exception_code).length,
    ],
    ["Completed", states.filter((state) => state === "COMPLETED").length],
  ] as const;
  return (
    <section className="space-y-4" aria-label="Dispatch operating overview">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {values.map(([label, value]) => (
          <Card className="p-4" key={label}>
            <p className="text-sm text-content-muted">{label}</p>
            <p className="mt-1 text-2xl font-bold">{value}</p>
          </Card>
        ))}
      </div>
      <Card className="p-4">
        <h3 className="font-semibold">Find operating work</h3>
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          <label className="text-sm font-medium">
            Search
            <Input
              className="mt-1"
              aria-label="Search Dispatch"
              value={search}
              onChange={(event) => onSearchChange(event.target.value)}
              placeholder="Customer, Job, address, technician"
            />
          </label>
          <label className="text-sm font-medium">
            Operating state
            <Select
              className="mt-1"
              aria-label="Dispatch operating state"
              value={filter}
              onChange={(event) =>
                onFilterChange(event.target.value as DispatchBoardFilter)
              }
            >
              <option value="all">All work</option>
              <option value="unassigned">Unassigned</option>
              <option value="active">Active work</option>
              <option value="exception">Exceptions</option>
              <option value="completed">Completed</option>
            </Select>
          </label>
          <label className="text-sm font-medium">
            Technician
            <Select
              className="mt-1"
              aria-label="Dispatch technician"
              value={technician}
              onChange={(event) => onTechnicianChange(event.target.value)}
            >
              <option value="">All assigned technicians</option>
              {technicians.map((name) => (
                <option key={name}>{name}</option>
              ))}
            </Select>
          </label>
        </div>
      </Card>
      <Card className="p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="font-semibold">Technician load and route context</h3>
            <p className="mt-1 text-sm text-content-muted">
              Booked windows and sequence only. Open space is not asserted
              availability or an autonomous routing decision.
            </p>
          </div>
          <Badge>{loads.length} technicians</Badge>
        </div>
        {loads.length ? (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[700px] text-left text-sm">
              <thead>
                <tr className="border-b border-stroke text-content-muted">
                  <th className="p-2">Technician</th>
                  <th className="p-2">Booked work</th>
                  <th className="p-2">Booked hours</th>
                  <th className="p-2">Overlaps</th>
                  <th className="p-2">Next work</th>
                  <th className="p-2">Location</th>
                </tr>
              </thead>
              <tbody>
                {loads.map((load) => (
                  <tr
                    className="border-b border-stroke last:border-0"
                    key={load.name}
                  >
                    <td className="p-2 font-semibold">{load.name}</td>
                    <td className="p-2">{load.appointments}</td>
                    <td className="p-2">{(load.minutes / 60).toFixed(1)}</td>
                    <td className="p-2">
                      {load.overlaps ? (
                        <span className="font-semibold text-status-danger-text">
                          {load.overlaps}
                        </span>
                      ) : (
                        "None"
                      )}
                    </td>
                    <td className="p-2">{load.nextJob ?? "Unavailable"}</td>
                    <td className="p-2">
                      {load.nextLocation ?? "Location unavailable"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="mt-4 text-sm text-content-muted">
            No assigned technician load appears in this authorized scope.
          </p>
        )}
      </Card>
      {items.some((item) => item.assignment?.active_exception_code) && (
        <Alert
          variant="warning"
          title="Dispatch exceptions require human review"
        >
          {items
            .filter((item) => item.assignment?.active_exception_code)
            .map(
              (item) =>
                `${item.appointment_number}: ${item.assignment?.active_exception_code?.replaceAll("_", " ")}`,
            )
            .join(" · ")}
        </Alert>
      )}
    </section>
  );
}
