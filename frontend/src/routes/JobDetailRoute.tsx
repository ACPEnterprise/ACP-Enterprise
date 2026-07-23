import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router";

import { AppointmentSummaryTable, CustomerSummaryCard, JobOperationalDetails, ServiceLocationCard } from "../components/jobs/JobDetailSections";
import { JobPriorityBadge, JobStatusBadge } from "../components/jobs/JobBadges";
import { JobsErrorState, JobsLoadingState } from "../components/jobs/JobStates";
import { LifecycleActionButtons } from "../components/jobs/LifecycleActionButtons";
import { useJob } from "../hooks/useJobs";

export function JobDetailRoute() {
  const { jobId } = useParams(); const query = useJob(jobId);
  if (query.isLoading) return <JobsLoadingState />;
  if (query.isError || !query.data) return <JobsErrorState error={query.error} onRetry={() => void query.refetch()} />;
  const job = query.data;
  return <div className="space-y-6"><Link className="inline-flex items-center gap-2 text-sm text-blue-400" to="/jobs"><ArrowLeft size={16} />Back to Jobs</Link><header className="flex flex-wrap items-start justify-between gap-4"><div><div className="flex flex-wrap items-center gap-2"><h2 className="text-3xl font-bold">{job.job_number}</h2><JobStatusBadge status={job.status} /><JobPriorityBadge priority={job.priority} /></div><p className="mt-2 text-slate-400">{job.customer_reported_problem ?? "No customer-reported problem"}</p></div><LifecycleActionButtons job={job} /></header><div className="grid gap-4 lg:grid-cols-2"><CustomerSummaryCard job={job} /><ServiceLocationCard job={job} /></div><JobOperationalDetails job={job} /><AppointmentSummaryTable job={job} /></div>;
}
