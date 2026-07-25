import { Link } from "react-router";
import type { JobListItem } from "../../types/jobs";
import { JobPriorityBadge, JobStatusBadge } from "./JobBadges";

export function JobsTable({ jobs }: { readonly jobs: readonly JobListItem[] }) {
  return <>
    <div className="grid gap-ui-3 p-ui-3 md:hidden" data-testid="jobs-mobile-cards">
      {jobs.map((job) => <article key={job.id} className="min-w-0 rounded-xl border border-stroke bg-surface-subtle p-ui-4">
        <div className="flex min-w-0 flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <Link className="break-all font-semibold text-action-primary hover:underline" to={`/jobs/${job.id}`}>{job.job_number}</Link>
            <p className="mt-1 break-words text-sm font-medium text-content">{job.customer_display_name}</p>
          </div>
          <div className="flex flex-wrap gap-2"><JobStatusBadge status={job.status} /><JobPriorityBadge priority={job.priority} /></div>
        </div>
        <dl className="mt-ui-3 grid min-w-0 gap-ui-3 text-sm">
          <div><dt className="text-content-muted">Service location</dt><dd className="break-words">{job.service_location_label}</dd></div>
          <div><dt className="text-content-muted">Reported problem</dt><dd className="break-words">{job.customer_reported_problem_summary ?? "No reported problem"}</dd></div>
          <div><dt className="text-content-muted">Appointment</dt><dd>{job.earliest_appointment_start_at ? new Date(job.earliest_appointment_start_at).toLocaleString() : "Not scheduled"}</dd></div>
          <div><dt className="text-content-muted">Updated</dt><dd>{new Date(job.updated_at).toLocaleDateString()}</dd></div>
        </dl>
      </article>)}
    </div>
    <div className="hidden overflow-x-auto md:block" data-testid="jobs-desktop-table">
      <table className="w-full text-left text-sm"><thead className="border-b border-stroke text-content-muted"><tr><th className="p-4">Job</th><th>Customer</th><th>Status</th><th>Priority</th><th>Appointment</th><th>Updated</th></tr></thead><tbody>{jobs.map((job) => <tr key={job.id} className="border-b border-stroke"><td className="p-4"><Link className="font-semibold text-action-primary hover:underline" to={`/jobs/${job.id}`}>{job.job_number}</Link><p className="mt-1 max-w-md break-words text-xs text-content-muted">{job.customer_reported_problem_summary ?? "No reported problem"}</p></td><td><p className="break-words">{job.customer_display_name}</p><p className="break-words text-xs text-content-muted">{job.service_location_label}</p></td><td><JobStatusBadge status={job.status} /></td><td><JobPriorityBadge priority={job.priority} /></td><td>{job.earliest_appointment_start_at ? new Date(job.earliest_appointment_start_at).toLocaleString() : "Not scheduled"}</td><td>{new Date(job.updated_at).toLocaleDateString()}</td></tr>)}</tbody></table>
    </div>
  </>;
}
