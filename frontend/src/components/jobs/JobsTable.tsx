import { Link } from "react-router";
import type { JobListItem } from "../../types/jobs";
import { JobPriorityBadge, JobStatusBadge } from "./JobBadges";

export function JobsTable({ jobs }: { readonly jobs: readonly JobListItem[] }) {
  return <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="border-b border-slate-800 text-slate-400"><tr><th className="p-4">Job</th><th>Customer</th><th>Status</th><th>Priority</th><th>Appointment</th><th>Updated</th></tr></thead><tbody>{jobs.map((job) => <tr key={job.id} className="border-b border-slate-800/70"><td className="p-4"><Link className="font-semibold text-blue-400 hover:underline" to={`/jobs/${job.id}`}>{job.job_number}</Link><p className="mt-1 max-w-md truncate text-xs text-slate-500">{job.customer_reported_problem_summary ?? "No reported problem"}</p></td><td><p>{job.customer_display_name}</p><p className="text-xs text-slate-500">{job.service_location_label}</p></td><td><JobStatusBadge status={job.status} /></td><td><JobPriorityBadge priority={job.priority} /></td><td>{job.earliest_appointment_start_at ? new Date(job.earliest_appointment_start_at).toLocaleString() : "Not scheduled"}</td><td>{new Date(job.updated_at).toLocaleDateString()}</td></tr>)}</tbody></table></div>;
}
