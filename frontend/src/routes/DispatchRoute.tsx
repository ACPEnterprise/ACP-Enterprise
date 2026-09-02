import { useState } from "react";
import { Link } from "react-router";

import { useAuth, useHasPermission } from "../auth";
import {
  DispatchJobsQueue,
  DispatchWorkQueue,
} from "../components/dispatch/DispatchQueues";
import { DispatchAssignmentPanel } from "../components/dispatch/DispatchAssignmentPanel";
import { DispatchScopeControls } from "../components/dispatch/DispatchScopeControls";
import { DispatchSummary } from "../components/dispatch/DispatchSummary";
import { DispatchWorkspaceLayout } from "../components/dispatch/DispatchWorkspaceLayout";
import {
  dayRange,
  localDateValue,
  operationalJobStatuses,
} from "../components/dispatch/dispatchPresentation";
import { useJobs } from "../hooks/useJobs";
import { useDispatchBoard } from "../hooks/useDispatch";
import type { DispatchBoardItem } from "../types/dispatch";
import { Alert } from "../ui";

export function DispatchRoute() {
  const { activeCompany } = useAuth();
  const canRead = useHasPermission("COMPANY_DISPATCH_READ");
  const canManage = useHasPermission("COMPANY_DISPATCH_MANAGE");
  const canReadJobs = useHasPermission("COMPANY_JOB_READ");
  const [date, setDate] = useState(() => localDateValue(new Date()));
  const [branchId, setBranchId] = useState("");
  const [jobPage, setJobPage] = useState(1);
  const [selectedWork, setSelectedWork] = useState<DispatchBoardItem | null>(
    null,
  );
  const range = dayRange(date);
  const dispatch = useDispatchBoard(
    range.startAt,
    range.endAt,
    branchId || undefined,
    canRead,
  );
  const jobs = useJobs(
    {
      branchId: branchId || undefined,
      status: operationalJobStatuses,
      page: jobPage,
      pageSize: 20,
      sortField: "priority",
      sortDirection: "desc",
    },
    canRead && canReadJobs,
  );
  if (!activeCompany)
    return (
      <Alert variant="danger" title="Company scope unavailable">
        Select an accessible Company before opening Dispatch.
      </Alert>
    );
  if (!canRead)
    return (
      <Alert variant="danger">You are not authorized to view Dispatch.</Alert>
    );
  const changeDate = (value: string) => {
    setDate(value);
    setSelectedWork(null);
  };
  const changeBranch = (value: string) => {
    setBranchId(value);
    setSelectedWork(null);
    setJobPage(1);
  };
  return (
    <div className="min-w-0 space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-action-primary">Operations</p>
          <h2 className="mt-1 text-2xl font-bold sm:text-3xl">Dispatch</h2>
          <p className="mt-2 text-content-muted">
            Assign eligible technicians to scheduled work and monitor
            operational Jobs.
          </p>
        </div>
        <Link
          className="inline-flex min-h-11 items-center rounded-lg bg-action-primary px-4 font-semibold text-white"
          to="/scheduling"
        >
          Open calendar
        </Link>
      </header>
      <DispatchScopeControls
        date={date}
        branchId={branchId}
        branches={activeCompany.branches}
        onDateChange={changeDate}
        onBranchChange={changeBranch}
      />
      <DispatchSummary
        appointmentTotal={dispatch.data?.total_count ?? 0}
        jobTotal={jobs.data?.total_count ?? 0}
        visibleJobs={jobs.data?.items ?? []}
      />
      {selectedWork && canManage && (
        <DispatchAssignmentPanel
          item={selectedWork}
          onClose={() => setSelectedWork(null)}
        />
      )}
      <DispatchWorkspaceLayout
        appointments={
          <DispatchWorkQueue
            items={dispatch.data?.items}
            loading={dispatch.isLoading}
            error={dispatch.error}
            onRetry={() => void dispatch.refetch()}
            onSelect={setSelectedWork}
            canManage={canManage}
          />
        }
        jobs={
          canReadJobs ? (
            <DispatchJobsQueue
              jobs={jobs.data?.items}
              loading={jobs.isLoading}
              error={jobs.error}
              onRetry={() => void jobs.refetch()}
              page={jobPage}
              totalPages={jobs.data?.total_pages ?? 0}
              onPageChange={setJobPage}
            />
          ) : (
            <Alert>Operational Jobs require Job read authority.</Alert>
          )
        }
      />
    </div>
  );
}
