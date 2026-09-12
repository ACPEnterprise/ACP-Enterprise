import { ArrowLeft } from "lucide-react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";

import {
  AppointmentSummaryTable,
  CustomerSummaryCard,
  JobOperationalDetails,
  ServiceLocationCard,
} from "../components/jobs/JobDetailSections";
import { JobPriorityBadge, JobStatusBadge } from "../components/jobs/JobBadges";
import { JobsErrorState, JobsLoadingState } from "../components/jobs/JobStates";
import { LifecycleActionButtons } from "../components/jobs/LifecycleActionButtons";
import { JobCompletionStatus } from "../components/jobs/JobCompletionStatus";
import { ScheduleJobPanel } from "../components/jobs/ScheduleJobPanel";
import { useHasPermission } from "../auth";
import { useJob } from "../hooks/useJobs";
import { schedulingReturnPath } from "../routing/paths";
import { Alert, Button } from "../ui";

export function JobDetailRoute() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const returnTo = schedulingReturnPath(searchParams.get("returnTo"));
  const hasSchedulingReturn = searchParams.has("returnTo") && returnTo !== "/scheduling";
  const canRead = useHasPermission("COMPANY_JOB_READ");
  const canReadCustomer = useHasPermission("COMPANY_CUSTOMER_READ");
  const canExecute = useHasPermission("COMPANY_JOB_EXECUTE");
  const canManageScheduling = useHasPermission("COMPANY_SCHEDULING_MANAGE");
  const canManageJobs = useHasPermission("COMPANY_JOB_MANAGE");
  const canSchedule = canManageScheduling && canManageJobs;
  const canAssign = useHasPermission("COMPANY_DISPATCH_MANAGE");
  const query = useJob(jobId, canRead);
  if (!canRead) {
    return <Alert variant="danger">You are not authorized to view this Job.</Alert>;
  }
  if (query.isLoading) return <JobsLoadingState />;
  if (query.isError || !query.data) {
    return (
      <JobsErrorState
        error={query.error}
        onRetry={() => void query.refetch()}
      />
    );
  }
  const job = query.data;
  return (
    <div className="min-w-0 space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          className="inline-flex min-h-11 items-center gap-2 text-sm text-action-primary"
          to={hasSchedulingReturn ? returnTo : "/jobs"}
        >
          <ArrowLeft size={16} /> {hasSchedulingReturn ? "Back to Schedule" : "Back to Jobs"}
        </Link>
        {canReadCustomer && jobId ? (
          <Button
            variant="secondary"
            onClick={() =>
              navigate(
                `/lia?contextDomain=jobs&contextId=${encodeURIComponent(jobId)}`,
              )
            }
          >
            Ask LIA about this Job
          </Button>
        ) : null}
      </div>
      <header className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_auto]">
        <div className="min-w-0">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h2 className="break-all text-2xl font-bold sm:text-3xl">
              {job.job_number}
            </h2>
            <JobStatusBadge status={job.status} />
            <JobPriorityBadge priority={job.priority} />
          </div>
          <p className="mt-2 whitespace-pre-wrap break-words text-content-muted">
            {job.customer_reported_problem ?? "No customer-reported problem"}
          </p>
        </div>
        {canExecute && <LifecycleActionButtons job={job} />}
      </header>
      <div className="grid min-w-0 gap-4 lg:grid-cols-2">
        <CustomerSummaryCard job={job} canOpenCustomer={canReadCustomer} returnTo={hasSchedulingReturn ? returnTo : undefined} />
        <ServiceLocationCard job={job} />
      </div>
      <JobOperationalDetails job={job} />
      {canSchedule && job.appointments.length === 0 && !["completed", "cancelled"].includes(job.status) ? <ScheduleJobPanel job={job} canAssign={canAssign} /> : null}
      <AppointmentSummaryTable job={job} returnTo={hasSchedulingReturn ? returnTo : undefined} />
      <JobCompletionStatus jobId={job.id} />
    </div>
  );
}
