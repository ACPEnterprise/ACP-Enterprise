import { Link } from "react-router";

import type { DispatchBoardItem } from "../../types/dispatch";
import type { JobListItem, JobPriority, JobStatus } from "../../types/jobs";
import type { AppointmentDetail } from "../../types/scheduling";
import { appointmentDetailPath, customerDetailPath, customerLocationPath, jobDetailPath, withSchedulingReturn } from "../../routing/paths";
import { Badge, Button, Card, Select } from "../../ui";

export type QueueAssignmentFilter = "needs_attention" | "scheduled_unassigned" | "assigned" | "all";
export type QueueSort = "oldest" | "newest" | "priority";

interface NeedsSchedulingQueueProps {
  readonly jobs: readonly JobListItem[];
  readonly appointments: readonly AppointmentDetail[];
  readonly dispatchByAppointment: ReadonlyMap<string, DispatchBoardItem>;
  readonly jobsById: ReadonlyMap<string, JobListItem>;
  readonly branches: readonly { id: string; name: string }[];
  readonly search: string;
  readonly jobStatus: JobStatus | "";
  readonly priority: JobPriority | "";
  readonly assignmentFilter: QueueAssignmentFilter;
  readonly sort: QueueSort;
  readonly returnTo: string;
  readonly onJobStatusChange: (value: JobStatus | "") => void;
  readonly onPriorityChange: (value: JobPriority | "") => void;
  readonly onAssignmentFilterChange: (value: QueueAssignmentFilter) => void;
  readonly onSortChange: (value: QueueSort) => void;
  readonly onSelect: (item: AppointmentDetail) => void;
}

const jobStatuses: readonly JobStatus[] = ["draft", "ready", "in_progress", "paused"];
const priorities: readonly JobPriority[] = ["low", "normal", "high", "urgent", "emergency"];
const priorityOrder: Record<JobPriority, number> = { low: 0, normal: 1, high: 2, urgent: 3, emergency: 4 };
const activeAssignment = (item?: DispatchBoardItem) => item?.assignment && !["released", "replaced", "cancelled"].includes(item.assignment.status) ? item.assignment : null;
const classification = (appointment: AppointmentDetail, dispatch?: DispatchBoardItem) => {
  if (appointment.status === "draft" || !appointment.arrival_window_start_at) return "NEEDS_SCHEDULING";
  return activeAssignment(dispatch) ? "ASSIGNED" : "SCHEDULED_UNASSIGNED";
};
const dateTime = (value: string | null) => value ? new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "Not established";

export function NeedsSchedulingQueue(props: NeedsSchedulingQueueProps) {
  const branchName = (id: string) => props.branches.find((branch) => branch.id === id)?.name ?? "Accessible Branch";
  const search = props.search.trim().toLowerCase();
  const matchesJob = (job?: JobListItem) => Boolean(job &&
    (!props.jobStatus || job.status === props.jobStatus) &&
    (!props.priority || job.priority === props.priority) &&
    (!search || `${job.job_number} ${job.customer_display_name} ${job.service_location_label}`.toLowerCase().includes(search)));
  const unscheduled = (props.assignmentFilter === "needs_attention" || props.assignmentFilter === "all" ? props.jobs : [])
    .filter((job) => !job.earliest_appointment_start_at && matchesJob(job))
    .map((job) => ({ job, timestamp: job.created_at }));
  const projected = props.appointments.flatMap((appointment) => {
    const dispatch = props.dispatchByAppointment.get(appointment.id);
    const job = dispatch?.job_id ? props.jobsById.get(dispatch.job_id) : undefined;
    const state = classification(appointment, dispatch);
    const assignmentMatch = props.assignmentFilter === "all" ||
      (props.assignmentFilter === "needs_attention" && state !== "ASSIGNED") ||
      props.assignmentFilter === state.toLowerCase();
    const contextMatch = job ? matchesJob(job) : !props.jobStatus && !props.priority && (!search || appointment.appointment_number.toLowerCase().includes(search));
    return assignmentMatch && contextMatch ? [{ appointment, dispatch, job, state, created: appointment.created_at ?? appointment.updated_at ?? appointment.arrival_window_start_at ?? "" }] : [];
  });
  const compare = (left: { created: string; priority?: JobPriority }, right: { created: string; priority?: JobPriority }) => {
    if (props.sort === "priority") return (priorityOrder[right.priority ?? "normal"] - priorityOrder[left.priority ?? "normal"]) || left.created.localeCompare(right.created);
    return props.sort === "newest" ? right.created.localeCompare(left.created) : left.created.localeCompare(right.created);
  };
  unscheduled.sort((a, b) => compare({ created: a.timestamp, priority: a.job.priority }, { created: b.timestamp, priority: b.job.priority }));
  projected.sort((a, b) => compare({ created: a.created, priority: a.job?.priority }, { created: b.created, priority: b.job?.priority }));
  const count = unscheduled.length + projected.length;

  return <Card className="min-w-0 p-4" aria-label="Needs scheduling work queue">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h2 className="text-lg font-semibold">Needs Scheduling work queue</h2><p className="text-sm text-content-muted">Native Jobs and Appointments in the current authorized Branch, date, and filter scope.</p></div>
      <Badge>{count}</Badge>
    </div>
    <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <label className="text-sm font-medium">Queue state<Select className="mt-1" aria-label="Queue state" value={props.assignmentFilter} onChange={(event) => props.onAssignmentFilterChange(event.target.value as QueueAssignmentFilter)}><option value="needs_attention">Needs attention</option><option value="scheduled_unassigned">Scheduled, unassigned</option><option value="assigned">Assigned</option><option value="all">All projected work</option></Select></label>
      <label className="text-sm font-medium">Job status<Select className="mt-1" aria-label="Queue Job status" value={props.jobStatus} onChange={(event) => props.onJobStatusChange(event.target.value as JobStatus | "")}><option value="">All open Job statuses</option>{jobStatuses.map((value) => <option value={value} key={value}>{value.replaceAll("_", " ")}</option>)}</Select></label>
      <label className="text-sm font-medium">Priority<Select className="mt-1" aria-label="Queue priority" value={props.priority} onChange={(event) => props.onPriorityChange(event.target.value as JobPriority | "")}><option value="">All priorities</option>{priorities.map((value) => <option value={value} key={value}>{value}</option>)}</Select></label>
      <label className="text-sm font-medium">Order<Select className="mt-1" aria-label="Queue order" value={props.sort} onChange={(event) => props.onSortChange(event.target.value as QueueSort)}><option value="oldest">Oldest created first</option><option value="newest">Newest created first</option><option value="priority">Explicit priority, then oldest</option></Select></label>
    </div>

    <div className="mt-5 space-y-3">
      {projected.map(({ appointment, dispatch, job, state, created }) => {
        const assignment = activeAssignment(dispatch);
        const partial = !dispatch || !job;
        return <article className="rounded-xl border border-stroke p-4" key={appointment.id}>
          <div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex flex-wrap gap-2"><Badge>{state}</Badge>{partial && <Badge>PARTIAL</Badge>}{job?.priority === "emergency" && <Badge>EMERGENCY</Badge>}</div><h3 className="mt-2 font-semibold">{job?.job_number ?? appointment.appointment_number}</h3><p className="text-sm">{job?.customer_display_name ?? "Customer/Job context unavailable"}</p><p className="text-sm text-content-muted">{job?.service_location_label ?? "Service Location unavailable"}</p></div><div className="text-right text-sm"><p>{branchName(appointment.branch_id)}</p><p className="text-content-muted">{created ? `Created ${new Date(created).toLocaleDateString()}` : "Created date unavailable"}</p></div></div>
          <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4"><div><dt className="text-content-muted">Job status</dt><dd>{job?.status?.replaceAll("_", " ") ?? "Unavailable"}</dd></div><div><dt className="text-content-muted">Arrival window</dt><dd>{dateTime(appointment.arrival_window_start_at)} – {appointment.arrival_window_end_at ? new Date(appointment.arrival_window_end_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "end unavailable"}</dd></div><div><dt className="text-content-muted">Expected duration</dt><dd>{appointment.expected_duration_minutes ? `${appointment.expected_duration_minutes} minutes` : "Unavailable"}</dd></div><div><dt className="text-content-muted">Technician</dt><dd>{assignment?.primary_employee_name ?? "Unassigned"}</dd></div></dl>
          {partial && <p className="mt-3 text-sm text-status-warning">Some Customer, Job, or Dispatch context is unavailable. Appointment timing remains authoritative.</p>}
          <div className="mt-4 flex flex-wrap gap-2"><Button variant="outline" onClick={() => props.onSelect(appointment)}>{state === "ASSIGNED" ? "Inspect assignment" : "Select for assignment"}</Button><Link className="inline-flex min-h-11 items-center rounded-lg border border-stroke px-3 font-semibold" to={withSchedulingReturn(appointmentDetailPath(appointment.id), props.returnTo)}>Open Appointment</Link>{job && <><Link className="inline-flex min-h-11 items-center rounded-lg border border-stroke px-3 font-semibold" to={withSchedulingReturn(jobDetailPath(job.id), props.returnTo)}>{state === "NEEDS_SCHEDULING" ? "Open Job to schedule" : "Open Job"}</Link><Link className="inline-flex min-h-11 items-center rounded-lg border border-stroke px-3 font-semibold" to={withSchedulingReturn(customerDetailPath(job.customer_id), props.returnTo)}>Open Customer</Link><Link className="inline-flex min-h-11 items-center rounded-lg border border-stroke px-3 font-semibold" to={withSchedulingReturn(customerLocationPath(job.customer_id, job.service_location_id), props.returnTo)}>Open Location</Link></>}</div>
        </article>;
      })}
      {unscheduled.map(({ job }) => <article className="rounded-xl border border-stroke p-4" key={job.id}><div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex flex-wrap gap-2"><Badge>NEEDS_SCHEDULING</Badge>{job.priority === "emergency" && <Badge>EMERGENCY</Badge>}</div><h3 className="mt-2 font-semibold">{job.job_number}</h3><p className="text-sm">{job.customer_display_name}</p><p className="text-sm text-content-muted">{job.service_location_label}</p></div><div className="text-right text-sm"><p>{branchName(job.branch_id)}</p><p className="text-content-muted">{job.created_at ? `Created ${new Date(job.created_at).toLocaleDateString()}` : "Created date unavailable"}</p></div></div><dl className="mt-3 grid gap-2 text-sm sm:grid-cols-3"><div><dt className="text-content-muted">Job status</dt><dd>{job.status?.replaceAll("_", " ") ?? "Unavailable"}</dd></div><div><dt className="text-content-muted">Priority</dt><dd>{job.priority ?? "Unavailable"}</dd></div><div><dt className="text-content-muted">Requested date/window</dt><dd>Not established</dd></div></dl><div className="mt-4 flex flex-wrap gap-2"><Link className="inline-flex min-h-11 items-center rounded-lg bg-action-primary px-3 font-semibold text-white" to={withSchedulingReturn(jobDetailPath(job.id), props.returnTo)}>Open Job to schedule</Link>{job.customer_id && <Link className="inline-flex min-h-11 items-center rounded-lg border border-stroke px-3 font-semibold" to={withSchedulingReturn(customerDetailPath(job.customer_id), props.returnTo)}>Open Customer</Link>}{job.customer_id && job.service_location_id && <Link className="inline-flex min-h-11 items-center rounded-lg border border-stroke px-3 font-semibold" to={withSchedulingReturn(customerLocationPath(job.customer_id, job.service_location_id), props.returnTo)}>Open Location</Link>}</div></article>)}
      {!count && <p className="rounded-xl border border-dashed border-stroke p-5 text-sm text-content-muted">No work matches this authorized queue scope. Change a filter or date; no missing value was treated as completed or assigned.</p>}
    </div>
  </Card>;
}
