import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import { getOperatorApiError } from "../api/errors";
import { CreateJobFromAppointmentPanel } from "../components/appointments/CreateJobFromAppointmentPanel";
import { useAuth, useHasPermission } from "../auth";
import { useCustomerDetail } from "../hooks/useCustomers";
import { useJobForAppointment } from "../hooks/useJobs";
import { useAppointment } from "../hooks/useScheduling";
import {
  useDispatchAssignment,
  useDispatchAssignmentHistory,
  useEligibleTechnicians,
} from "../hooks/useDispatch";
import { dispatchReadiness } from "../components/dispatch/dispatchEligibility";
import {
  customerDetailPath,
  customerLocationPath,
  jobDetailPath,
  schedulingReturnPath,
  withSchedulingReturn,
} from "../routing/paths";
import { Alert, Button, Card } from "../ui";

const jobEligibleStatuses = new Set([
  "draft",
  "scheduled",
  "confirmed",
  "completed",
]);
const displayStatus = (value: string) => value.replaceAll("_", " ");
const timestamp = (value: string | null) =>
  value ? new Date(value).toLocaleString() : "Not scheduled";

export function AppointmentDetailRoute() {
  const { appointmentId } = useParams();
  const [searchParams] = useSearchParams();
  const returnTo = schedulingReturnPath(searchParams.get("returnTo"));
  const relatedJobPath = (jobId: string) =>
    searchParams.has("returnTo")
      ? withSchedulingReturn(jobDetailPath(jobId), returnTo)
      : jobDetailPath(jobId);
  const contextPath = (path: string) =>
    searchParams.has("returnTo") ? withSchedulingReturn(path, returnTo) : path;
  const canRead = useHasPermission("COMPANY_SCHEDULING_READ");
  const canReadJobs = useHasPermission("COMPANY_JOB_READ");
  const canManageJobs = useHasPermission("COMPANY_JOB_MANAGE");
  const canReadCustomers = useHasPermission("COMPANY_CUSTOMER_READ");
  const canReadDispatch = useHasPermission("COMPANY_DISPATCH_READ");
  const appointmentQuery = useAppointment(appointmentId, canRead);
  const relatedQuery = useJobForAppointment(
    appointmentId,
    canRead && canReadJobs,
  );
  const [creating, setCreating] = useState(false);
  const { activeCompany } = useAuth();
  const appointment = appointmentQuery.data;
  const assignmentQuery = useDispatchAssignment(
    appointmentId,
    canRead && canReadDispatch,
  );
  const assignmentHistoryQuery = useDispatchAssignmentHistory(
    appointmentId,
    canRead && canReadDispatch,
  );
  const eligibilityQuery = useEligibleTechnicians(
    canRead && canReadDispatch ? appointmentId : undefined,
  );
  const customerQuery = useCustomerDetail(
    appointment?.customer_id ?? null,
    canRead && canReadCustomers,
  );
  if (!canRead)
    return (
      <Alert variant="danger">
        You are not authorized to view this Appointment.
      </Alert>
    );
  if (appointmentQuery.isLoading)
    return (
      <Card className="p-ui-6">
        <p>Loading Appointment…</p>
      </Card>
    );
  if (appointmentQuery.isError || !appointment) {
    const error = getOperatorApiError(appointmentQuery.error, "Appointment");
    return (
      <Alert
        variant="danger"
        title={error.title}
        action={
          error.retryable ? (
            <Button onClick={() => void appointmentQuery.refetch()}>
              Retry
            </Button>
          ) : undefined
        }
      >
        {error.message}
      </Alert>
    );
  }
  const relatedJob = relatedQuery.data?.items[0];
  const branch = activeCompany?.branches.find(
    (item) => item.id === appointment.branch_id,
  );
  const customer = customerQuery.data;
  const location = customer?.properties.find(
    (item) => item.id === appointment.service_location_id,
  );
  const eligible = jobEligibleStatuses.has(appointment.status);
  return (
    <div className="min-w-0 space-y-6">
      <Link
        className="inline-flex min-h-11 items-center gap-2 text-sm text-action-primary"
        to={returnTo}
      >
        <ArrowLeft size={16} />
        Back to Scheduling
      </Link>
      <header className="min-w-0">
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          <h2 className="break-all text-2xl font-bold sm:text-3xl">
            {appointment.appointment_number}
          </h2>
          <span className="rounded-full bg-status-information/15 px-3 py-1 text-sm capitalize text-status-information">
            {displayStatus(appointment.status)}
          </span>
        </div>
        <p className="mt-2 text-content-muted">
          Scheduled service details and authoritative Job relationship.
        </p>
      </header>
      <div className="grid min-w-0 gap-4 lg:grid-cols-2">
        <Card className="p-ui-4 sm:p-ui-6">
          <h3 className="font-semibold">Service</h3>
          <dl className="mt-4 grid gap-3 text-sm">
            <div>
              <dt className="text-content-muted">Branch</dt>
              <dd className="break-words">
                {branch
                  ? `${branch.name} (${branch.code})`
                  : "Accessible Branch"}
              </dd>
            </div>
            <div>
              <dt className="text-content-muted">Arrival window</dt>
              <dd className="grid gap-1 sm:block">
                <time>{timestamp(appointment.arrival_window_start_at)}</time>
                <span aria-hidden="true" className="hidden sm:inline">
                  {" "}
                  –{" "}
                </span>
                <span className="text-content-muted sm:hidden">through</span>
                <time>{timestamp(appointment.arrival_window_end_at)}</time>
              </dd>
            </div>
            <div>
              <dt className="text-content-muted">Expected duration</dt>
              <dd>
                {appointment.expected_duration_minutes
                  ? `${appointment.expected_duration_minutes} minutes`
                  : "Not specified"}
              </dd>
            </div>
          </dl>
        </Card>
        <Card className="p-ui-4 sm:p-ui-6">
          <h3 className="font-semibold">Customer and Service Location</h3>
          <p className="mt-3 break-words">
            {customer
              ? customer.business_name ||
                `${customer.first_name ?? ""} ${customer.last_name ?? ""}`.trim()
              : "Customer details unavailable"}
          </p>
          <address className="mt-2 break-words not-italic text-sm text-content-muted">
            {location ? (
              <>
                {location.address_line_1}
                {location.address_line_2 && (
                  <>
                    <br />
                    {location.address_line_2}
                  </>
                )}
                <br />
                {location.city}, {location.state} {location.postal_code}
              </>
            ) : (
              "Service Location details unavailable"
            )}
          </address>
          {canReadCustomers && (
            <div className="mt-4 flex flex-wrap gap-2">
              <Link
                className="inline-flex min-h-11 items-center rounded-lg border border-stroke px-3 font-semibold text-action-primary"
                to={contextPath(customerDetailPath(appointment.customer_id))}
              >
                Open Customer
              </Link>
              <Link
                className="inline-flex min-h-11 items-center rounded-lg border border-stroke px-3 font-semibold text-action-primary"
                to={contextPath(
                  customerLocationPath(
                    appointment.customer_id,
                    appointment.service_location_id,
                  ),
                )}
              >
                Open Location
              </Link>
            </div>
          )}
        </Card>
      </div>
      <Card className="p-ui-4 sm:p-ui-6">
        <h3 className="font-semibold">Dispatch assignment and readiness</h3>
        {!canReadDispatch ? (
          <p className="mt-3 text-sm text-content-muted">
            Assignment evidence requires Dispatch read authority.
          </p>
        ) : assignmentQuery.isLoading ? (
          <p className="mt-3 text-sm text-content-muted">
            Loading assignment evidence…
          </p>
        ) : assignmentQuery.data ? (
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <dl className="grid gap-3 text-sm">
              <div>
                <dt className="text-content-muted">Primary technician</dt>
                <dd>
                  {assignmentQuery.data.primary_employee_name ?? "Unassigned"}
                </dd>
              </div>
              <div>
                <dt className="text-content-muted">Assignment state</dt>
                <dd className="capitalize">
                  {displayStatus(assignmentQuery.data.status)} ·{" "}
                  {displayStatus(assignmentQuery.data.arrival_state)}
                </dd>
              </div>
              <div>
                <dt className="text-content-muted">Version</dt>
                <dd>{assignmentQuery.data.version}</dd>
              </div>
            </dl>
            <div>
              <h4 className="text-sm font-semibold">Additional crew</h4>
              {assignmentQuery.data.crew_members.length ? (
                <ul className="mt-2 space-y-1 text-sm">
                  {assignmentQuery.data.crew_members.map((member) => (
                    <li key={member.id}>{member.display_name}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-sm text-content-muted">
                  No additional crew assigned.
                </p>
              )}
            </div>
          </div>
        ) : (
          <p className="mt-3 text-sm text-content-muted">
            No current assignment evidence is available for this Appointment.
          </p>
        )}
        {canReadDispatch && eligibilityQuery.data && (
          <div className="mt-5 border-t border-stroke pt-4">
            <h4 className="text-sm font-semibold">Workforce readiness</h4>
            <ul className="mt-2 grid gap-2 sm:grid-cols-2">
              {eligibilityQuery.data.map((technician) => (
                <li
                  className="rounded-md bg-surface-muted p-3 text-sm"
                  key={technician.employee_id}
                >
                  <strong>{technician.display_name}</strong>
                  <span className="block text-content-muted">
                    {dispatchReadiness(technician).replaceAll("_", " ")}
                    {technician.reasons.length
                      ? ` · ${technician.reasons.map(displayStatus).join(" · ")}`
                      : ""}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>
      <Card className="p-ui-4 sm:p-ui-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="font-semibold">Scheduling history and source</h3>
            <p className="mt-1 text-sm text-content-muted">
              Authoritative Scheduling version and lifecycle evidence.
            </p>
          </div>
          <Button
            variant="outline"
            onClick={() => void appointmentQuery.refetch()}
          >
            Refresh Appointment
          </Button>
        </div>
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="text-content-muted">Version</dt>
            <dd>{appointment.concurrency_version}</dd>
          </div>
          <div>
            <dt className="text-content-muted">Times moved</dt>
            <dd>{appointment.reschedule_count}</dd>
          </div>
          <div>
            <dt className="text-content-muted">Last moved</dt>
            <dd>{timestamp(appointment.rescheduled_at)}</dd>
          </div>
          <div>
            <dt className="text-content-muted">Last updated</dt>
            <dd>{timestamp(appointment.updated_at)}</dd>
          </div>
          {appointment.cancelled_at && (
            <div>
              <dt className="text-content-muted">Canceled</dt>
              <dd>
                {timestamp(appointment.cancelled_at)} ·{" "}
                {appointment.cancellation_reason_code?.replaceAll("_", " ") ??
                  "reason unavailable"}
              </dd>
            </div>
          )}
          <div>
            <dt className="text-content-muted">Source</dt>
            <dd>Source identity is not exposed by this read contract</dd>
          </div>
        </dl>
        <p className="mt-3 text-xs text-content-muted">
          No source system, Estimate, Invoice, or technician history is inferred
          when its authoritative projection is unavailable. Open the related Job
          for supported commercial context.
        </p>
      </Card>
      {canReadDispatch && (
        <Card className="p-ui-4 sm:p-ui-6">
          <h3 className="font-semibold">Assignment history</h3>
          <p className="mt-1 text-sm text-content-muted">
            Durable assignment, reassignment, crew, arrival, and exception
            evidence.
          </p>
          {assignmentHistoryQuery.data?.length ? (
            <ol className="mt-4 space-y-3">
              {assignmentHistoryQuery.data.map((entry) => (
                <li
                  className="rounded-md border border-stroke p-3 text-sm"
                  key={`${entry.version}-${entry.occurred_at}`}
                >
                  <p className="font-semibold capitalize">
                    {displayStatus(entry.event_type)}
                  </p>
                  <p className="mt-1 text-content-muted">
                    {entry.actor_display_name} · {timestamp(entry.occurred_at)}{" "}
                    · version {entry.version}
                  </p>
                  <p className="mt-1">
                    {entry.prior_status
                      ? `${displayStatus(entry.prior_status)} → `
                      : ""}
                    {displayStatus(entry.new_status)} · {entry.reason}
                  </p>
                </li>
              ))}
            </ol>
          ) : (
            <p className="mt-3 text-sm text-content-muted">
              No assignment history is available.
            </p>
          )}
        </Card>
      )}
      <Card className="p-ui-4 sm:p-ui-6">
        <h3 className="font-semibold">Related Job</h3>
        {relatedJob ? (
          <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_auto] sm:items-center">
            <div className="min-w-0">
              <Link
                className="break-all font-semibold text-action-primary hover:underline"
                to={relatedJobPath(relatedJob.id)}
              >
                {relatedJob.job_number}
              </Link>
              <p className="mt-1 text-sm capitalize text-content-muted">
                {displayStatus(relatedJob.status)}
              </p>
            </div>
            <Link
              className="inline-flex min-h-11 w-full items-center justify-center rounded-md bg-action-primary px-ui-4 text-sm font-semibold text-content-inverse sm:w-auto"
              to={relatedJobPath(relatedJob.id)}
            >
              Open Job
            </Link>
          </div>
        ) : relatedQuery.isLoading ? (
          <p className="mt-3 text-sm text-content-muted">
            Checking for a related Job…
          </p>
        ) : (
          <div className="mt-3">
            <p className="text-sm text-content-muted">
              {canReadJobs
                ? relatedQuery.isError
                  ? "Related Job information is unavailable with your current access."
                  : "No Job has been created from this Appointment."
                : "Job details require Job read authority."}
            </p>
            {eligible && canManageJobs && (
              <Button
                className="mt-4 sm:w-auto"
                fullWidth
                onClick={() => setCreating(true)}
              >
                Create Job
              </Button>
            )}
            {!eligible && (
              <p className="mt-3 text-sm">
                This Appointment state is not eligible for Job creation.
              </p>
            )}
          </div>
        )}
      </Card>
      {creating && canManageJobs && !relatedJob && (
        <CreateJobFromAppointmentPanel
          appointment={appointment}
          onCancel={() => setCreating(false)}
        />
      )}
    </div>
  );
}
