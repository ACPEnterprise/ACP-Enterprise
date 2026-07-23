import type { JobDetail } from "../../types/jobs";
import { Card } from "../../ui";
import { useAuth } from "../../auth";
import { Link } from "react-router";
import { appointmentDetailPath } from "../../routing/paths";

export function CustomerSummaryCard({ job }: { readonly job: JobDetail }) {
  return <Card className="p-ui-6"><h3 className="font-semibold">Customer</h3><p className="mt-2">{job.customer.display_name}</p><p className="text-sm text-slate-500">{job.customer.customer_number}</p></Card>;
}
export function ServiceLocationCard({ job }: { readonly job: JobDetail }) {
  const location = job.service_location;
  return <Card className="p-ui-6"><h3 className="font-semibold">Service Location</h3><address className="mt-2 not-italic text-sm text-slate-300">{location.nickname && <strong className="block">{location.nickname}</strong>}{location.address_line_1}<br />{location.address_line_2 && <>{location.address_line_2}<br /></>}{location.city}, {location.state} {location.postal_code}</address></Card>;
}
export function AppointmentSummaryTable({ job }: { readonly job: JobDetail }) {
  return <Card className="p-ui-6"><h3 className="font-semibold">Appointments</h3>{job.appointments.length === 0 ? <p className="mt-3 text-sm text-slate-500">No Appointments linked.</p> : <div className="mt-3 divide-y divide-slate-800">{job.appointments.map((item) => <div className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm" key={item.appointment_id}><div><span className="text-content-muted">{item.visit_sequence}. </span><Link className="font-semibold text-blue-400 hover:underline" to={appointmentDetailPath(item.appointment_id)}>{item.appointment_number}</Link><p className="mt-1 capitalize text-content-muted">{item.status.replaceAll("_", " ")}</p></div><span className="text-slate-400">{item.arrival_window_start_at ? new Date(item.arrival_window_start_at).toLocaleString() : "No arrival window"}</span></div>)}</div>}</Card>;
}

const timestamp = (value: string | null) => value ? new Date(value).toLocaleString() : "Not recorded";

export function JobOperationalDetails({ job }: { readonly job: JobDetail }) {
  const { activeCompany } = useAuth();
  const branch = activeCompany?.branches.find((item) => item.id === job.branch_id);
  return <Card className="p-ui-6"><h3 className="font-semibold">Operational details</h3><dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
    <div><dt className="text-content-muted">Branch</dt><dd>{branch ? `${branch.name} (${branch.code})` : "Accessible Branch"}</dd></div>
    <div><dt className="text-content-muted">Job type</dt><dd>{job.job_type_code ?? "Not specified"}</dd></div>
    <div><dt className="text-content-muted">Created</dt><dd>{timestamp(job.created_at)}</dd></div>
    <div><dt className="text-content-muted">Updated</dt><dd>{timestamp(job.updated_at)}</dd></div>
    <div><dt className="text-content-muted">Activated</dt><dd>{timestamp(job.activated_at)}</dd></div>
    <div><dt className="text-content-muted">Started</dt><dd>{timestamp(job.started_at)}</dd></div>
    {job.paused_at && <div><dt className="text-content-muted">Paused</dt><dd>{timestamp(job.paused_at)} · {job.pause_reason_code?.replaceAll("_", " ")}</dd></div>}
    {job.completed_at && <div><dt className="text-content-muted">Last completed</dt><dd>{timestamp(job.completed_at)}</dd></div>}
    {job.cancelled_at && <div><dt className="text-content-muted">Last cancelled</dt><dd>{timestamp(job.cancelled_at)} · {job.cancellation_reason_code?.replaceAll("_", " ")}</dd></div>}
  </dl>{job.internal_description && <div className="mt-5 border-t border-stroke pt-4"><h4 className="text-sm font-semibold">Internal description</h4><p className="mt-2 whitespace-pre-wrap text-sm text-content-secondary">{job.internal_description}</p></div>}</Card>;
}
