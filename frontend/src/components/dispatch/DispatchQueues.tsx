import { Link } from "react-router";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { getOperatorApiError } from "../../api/errors";
import { appointmentDetailPath, jobDetailPath } from "../../routing/paths";
import type { JobListItem } from "../../types/jobs";
import type { AppointmentDetail } from "../../types/scheduling";
import type { DispatchBoardItem } from "../../types/dispatch";
import { Alert, Button, Card, EmptyState, Spinner } from "../../ui";
import { JobPriorityBadge, JobStatusBadge } from "../jobs/JobBadges";

const time = (value: string | null) =>
  value
    ? new Date(value).toLocaleTimeString([], {
        hour: "numeric",
        minute: "2-digit",
      })
    : "Time not set";

export function DispatchAppointmentsQueue({
  appointments,
  loading,
  error,
  onRetry,
  page,
  totalPages,
  onPageChange,
}: {
  readonly appointments?: readonly AppointmentDetail[];
  readonly loading: boolean;
  readonly error: unknown;
  readonly onRetry: () => void;
  readonly page: number;
  readonly totalPages: number;
  readonly onPageChange: (page: number) => void;
}) {
  return (
    <section
      className="min-w-0"
      aria-labelledby="dispatch-appointments-heading"
    >
      <h3 id="dispatch-appointments-heading" className="text-xl font-semibold">
        Appointments
      </h3>
      <p className="mt-1 text-sm text-content-muted">
        Arrival-ordered scheduled work in the selected scope.
      </p>
      <Card className="mt-3 overflow-hidden">
        {loading ? (
          <div className="flex justify-center p-ui-8">
            <Spinner label="Loading Appointments" />
          </div>
        ) : error ? (
          <div className="p-ui-4">
            <SectionError
              resource="Appointments"
              error={error}
              onRetry={onRetry}
            />
          </div>
        ) : appointments?.length ? (
          <div className="divide-y divide-stroke">
            {appointments.map((appointment) => (
              <article
                className="flex min-w-0 flex-col gap-3 p-ui-4 sm:flex-row sm:items-center sm:justify-between"
                key={appointment.id}
              >
                <div className="min-w-0">
                  <Link
                    className="break-all font-semibold text-action-primary hover:underline"
                    to={appointmentDetailPath(appointment.id)}
                  >
                    {appointment.appointment_number}
                  </Link>
                  <p className="mt-1 break-words text-sm capitalize text-content-muted">
                    {appointment.status.replaceAll("_", " ")} ·{" "}
                    {appointment.expected_duration_minutes
                      ? `${appointment.expected_duration_minutes} min`
                      : "Duration not set"}
                  </p>
                </div>
                <div className="min-w-0 sm:text-right">
                  <p className="break-words font-medium">
                    {time(appointment.arrival_window_start_at)} –{" "}
                    {time(appointment.arrival_window_end_at)}
                  </p>
                  <Link
                    className="mt-1 inline-flex min-h-11 items-center text-sm text-action-primary hover:underline"
                    to={appointmentDetailPath(appointment.id)}
                  >
                    Open Appointment
                  </Link>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            title="No Appointments"
            description="No Appointments fall within this date and Branch scope."
          />
        )}
        {!loading && !error && totalPages > 1 && (
          <QueuePagination
            label="Appointment"
            page={page}
            totalPages={totalPages}
            onPageChange={onPageChange}
          />
        )}
      </Card>
    </section>
  );
}

export function DispatchJobsQueue({
  jobs,
  loading,
  error,
  onRetry,
  page,
  totalPages,
  onPageChange,
}: {
  readonly jobs?: readonly JobListItem[];
  readonly loading: boolean;
  readonly error: unknown;
  readonly onRetry: () => void;
  readonly page: number;
  readonly totalPages: number;
  readonly onPageChange: (page: number) => void;
}) {
  return (
    <section className="min-w-0" aria-labelledby="dispatch-jobs-heading">
      <h3 id="dispatch-jobs-heading" className="text-xl font-semibold">
        Operational Jobs
      </h3>
      <p className="mt-1 text-sm text-content-muted">
        Nonterminal Jobs requiring operational awareness.
      </p>
      <Card className="mt-3 overflow-hidden">
        {loading ? (
          <div className="flex justify-center p-ui-8">
            <Spinner label="Loading operational Jobs" />
          </div>
        ) : error ? (
          <div className="p-ui-4">
            <SectionError resource="Jobs" error={error} onRetry={onRetry} />
          </div>
        ) : jobs?.length ? (
          <div className="divide-y divide-stroke">
            {jobs.map((job) => (
              <article
                className="flex min-w-0 flex-col gap-3 p-ui-4 sm:flex-row sm:items-center sm:justify-between"
                key={job.id}
              >
                <div className="min-w-0">
                  <Link
                    className="break-all font-semibold text-action-primary hover:underline"
                    to={jobDetailPath(job.id)}
                  >
                    {job.job_number}
                  </Link>
                  <p className="mt-1 break-words text-sm text-content-muted">
                    {job.customer_display_name} · {job.service_location_label}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-surface-muted px-ui-2 py-ui-1 text-xs font-semibold text-content-secondary">
                    {job.earliest_appointment_start_at
                      ? "Scheduled"
                      : "Unscheduled"}
                  </span>
                  <JobPriorityBadge priority={job.priority} />
                  <JobStatusBadge status={job.status} />
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            title="No operational Jobs"
            description="No draft, ready, active, or paused Jobs match this Branch scope."
          />
        )}
        {!loading && !error && totalPages > 1 && (
          <QueuePagination
            label="Job"
            page={page}
            totalPages={totalPages}
            onPageChange={onPageChange}
          />
        )}
      </Card>
    </section>
  );
}

function QueuePagination({
  label,
  page,
  totalPages,
  onPageChange,
}: {
  readonly label: string;
  readonly page: number;
  readonly totalPages: number;
  readonly onPageChange: (page: number) => void;
}) {
  return (
    <footer className="flex flex-col gap-3 border-t border-stroke p-ui-3 text-sm text-content-muted sm:flex-row sm:items-center sm:justify-between">
      <span>
        Page {page} of {totalPages}
      </span>
      <div className="grid grid-cols-2 gap-2 sm:flex">
        <Button
          variant="outline"
          aria-label={`Previous ${label} page`}
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          <ChevronLeft size={17} />
        </Button>
        <Button
          variant="outline"
          aria-label={`Next ${label} page`}
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
        >
          <ChevronRight size={17} />
        </Button>
      </div>
    </footer>
  );
}

function SectionError({
  resource,
  error,
  onRetry,
}: {
  readonly resource: string;
  readonly error: unknown;
  readonly onRetry: () => void;
}) {
  const value = getOperatorApiError(error, resource);
  return (
    <Alert
      variant="danger"
      title={`${resource} unavailable`}
      action={
        value.retryable ? <Button onClick={onRetry}>Retry</Button> : undefined
      }
    >
      {value.message}
    </Alert>
  );
}

export function DispatchWorkQueue({
  items,
  loading,
  error,
  onRetry,
  onSelect,
}: {
  readonly items?: readonly DispatchBoardItem[];
  readonly loading: boolean;
  readonly error: unknown;
  readonly onRetry: () => void;
  readonly onSelect: (item: DispatchBoardItem) => void;
}) {
  return (
    <section className="min-w-0" aria-labelledby="dispatch-work-heading">
      <h3 id="dispatch-work-heading" className="text-xl font-semibold">
        Scheduled work
      </h3>
      <p className="mt-1 text-sm text-content-muted">
        Authoritative Appointment timing and technician assignment.
      </p>
      <Card className="mt-3 overflow-hidden">
        {loading ? (
          <div className="flex justify-center p-ui-8">
            <Spinner label="Loading Dispatch board" />
          </div>
        ) : error ? (
          <div className="p-ui-4">
            <SectionError
              resource="Dispatch board"
              error={error}
              onRetry={onRetry}
            />
          </div>
        ) : items?.length ? (
          <div className="divide-y divide-stroke">
            {items.map((item) => (
              <article
                className="flex flex-col gap-3 p-ui-4 sm:flex-row sm:items-center sm:justify-between"
                key={item.appointment_id}
              >
                <div>
                  <p className="font-semibold">{item.appointment_number}</p>
                  <p className="mt-1 text-sm text-content-muted">
                    {time(item.window_start_at)} – {time(item.window_end_at)} ·{" "}
                    {item.assignment?.primary_employee_name ?? "Unassigned"}
                  </p>
                  <p className="mt-1 text-xs font-semibold capitalize text-content-secondary">
                    {item.assignment?.status.replaceAll("_", " ") ??
                      "Assignment needed"}
                  </p>
                </div>
                <Button onClick={() => onSelect(item)}>
                  {item.assignment ? "Manage assignment" : "Assign technician"}
                </Button>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            title="No scheduled work"
            description="No assignable Appointments fall within this scope."
          />
        )}
      </Card>
    </section>
  );
}
