import type { JobListItem } from "../../types/jobs";
import type { AppointmentDetail } from "../../types/scheduling";
import { Alert, Badge, Card } from "../../ui";
import {
  buildCalendarGraphReadiness,
  CURRENT_CALENDAR_SOURCE_BASELINE,
} from "./calendarOperations";

export function CalendarReadinessCard({
  appointments,
  appointmentTotal,
  jobs,
  jobTotal,
  unavailable = false,
}: {
  readonly appointments: readonly AppointmentDetail[];
  readonly appointmentTotal: number;
  readonly jobs: readonly JobListItem[];
  readonly jobTotal: number;
  readonly unavailable?: boolean;
}) {
  const complete =
    !unavailable &&
    appointments.length === appointmentTotal &&
    jobs.length === jobTotal;
  const value = buildCalendarGraphReadiness(appointments, jobs, complete);
  const baseline = CURRENT_CALENDAR_SOURCE_BASELINE;
  return (
    <Card className="p-4" aria-label="Current calendar completeness">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-action-primary">
            Current operating graph
          </p>
          <h2 className="mt-1 text-lg font-semibold">Calendar completeness</h2>
          <p className="mt-1 text-sm text-content-muted">
          Native ACP visibility compared with admitted {baseline.contract}
            evidence as of {baseline.asOf}.
          </p>
        </div>
        <Badge>{value.state}</Badge>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <ReadinessCount
          label="Customers"
          observed={value.customers}
          expected={baseline.customers}
        />
        <ReadinessCount
          label="Locations"
          observed={value.locations}
          expected={baseline.locations}
        />
        <ReadinessCount
          label="Jobs"
          observed={value.jobs}
          expected={baseline.jobs}
        />
        <ReadinessCount
          label="Current/future appointments"
          observed={value.currentFutureAppointments}
          expected={baseline.currentFutureAppointments}
        />
      </div>
      <p className="mt-3 text-xs text-content-muted">
        The admitted source graph contains {baseline.appointments} Appointments
        total; {baseline.currentFutureAppointments} belong to the bounded
        current/future subset. Historical or held evidence is not presented as
        active calendar work.
      </p>
      {value.state === "PARTIAL" && (
        <Alert
          className="mt-4"
          variant="warning"
          title="Completeness unavailable"
        >
          ACP did not receive every native row in the bounded query. No missing
          count is inferred until the full authorized projection loads.
        </Alert>
      )}
      {value.state === "INCOMPLETE" && (
        <Alert
          className="mt-4"
          variant="warning"
          title="Calendar graph requires attention"
        >
          Native visibility differs from the admitted snapshot:{" "}
          {value.missing.join(", ")}. Review Migration admission and native
          parent links before treating the calendar as complete.
        </Alert>
      )}
    </Card>
  );
}

function ReadinessCount({
  label,
  observed,
  expected,
}: {
  readonly label: string;
  readonly observed: number;
  readonly expected: number;
}) {
  return (
    <div className="rounded-lg border border-stroke p-3">
      <p className="text-xs text-content-muted">{label}</p>
      <p className="mt-1 text-lg font-semibold">
        {observed}{" "}
        <span className="text-sm font-normal text-content-muted">
          / {expected}
        </span>
      </p>
    </div>
  );
}
