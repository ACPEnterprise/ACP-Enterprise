import { useMemo, useState } from "react";
import { Link } from "react-router";

import { useAuth, useHasPermission } from "../auth";
import {
  DispatchJobsQueue,
  DispatchWorkQueue,
} from "../components/dispatch/DispatchQueues";
import { DispatchAssignmentPanel } from "../components/dispatch/DispatchAssignmentPanel";
import { DispatchRecommendationPanel } from "../components/dispatch/DispatchRecommendationPanel";
import { DispatchScopeControls } from "../components/dispatch/DispatchScopeControls";
import { DispatchSummary } from "../components/dispatch/DispatchSummary";
import { DispatchWorkspaceLayout } from "../components/dispatch/DispatchWorkspaceLayout";
import { DispatchOperationsOverview } from "../components/dispatch/DispatchOperationsOverview";
import {
  filterDispatchBoard,
  type DispatchBoardFilter,
} from "../components/dispatch/dispatchOperations";
import {
  dayRange,
  localDateValue,
  operationalJobStatuses,
} from "../components/dispatch/dispatchPresentation";
import { useJobs } from "../hooks/useJobs";
import { useDispatchBoard } from "../hooks/useDispatch";
import { Alert } from "../ui";

export function DispatchRoute() {
  const { activeCompany } = useAuth();
  const canRead = useHasPermission("COMPANY_DISPATCH_READ");
  const canManage = useHasPermission("COMPANY_DISPATCH_MANAGE");
  const canReadJobs = useHasPermission("COMPANY_JOB_READ");
  const [date, setDate] = useState(() => localDateValue(new Date()));
  const [branchId, setBranchId] = useState("");
  const [jobPage, setJobPage] = useState(1);
  const [boardFilter, setBoardFilter] = useState<DispatchBoardFilter>("all");
  const [search, setSearch] = useState("");
  const [technician, setTechnician] = useState("");
  const [selectedAppointmentId, setSelectedAppointmentId] = useState<string | null>(null);
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
  const jobsById = useMemo(
    () => new Map((jobs.data?.items ?? []).map((job) => [job.id, job])),
    [jobs.data?.items],
  );
  const dispatchItems = dispatch.data?.items ?? [];
  const selectedWork = selectedAppointmentId
    ? dispatchItems.find((item) => item.appointment_id === selectedAppointmentId) ?? null
    : null;
  const visibleDispatchItems = filterDispatchBoard(
    dispatchItems,
    jobsById,
    boardFilter,
    search,
    technician,
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
    setSelectedAppointmentId(null);
  };
  const changeBranch = (value: string) => {
    setBranchId(value);
    setSelectedAppointmentId(null);
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
          to="/scheduling?perspective=dispatch"
        >
          Open Dispatch calendar
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
      <DispatchOperationsOverview
        items={dispatchItems}
        jobsById={jobsById}
        filter={boardFilter}
        search={search}
        technician={technician}
        onFilterChange={setBoardFilter}
        onSearchChange={setSearch}
        onTechnicianChange={setTechnician}
      />
      {selectedWork && canManage && (
        <DispatchAssignmentPanel
          item={selectedWork}
          onClose={() => setSelectedAppointmentId(null)}
        />
      )}
      {selectedWork && canReadJobs && (
        <DispatchRecommendationPanel item={selectedWork} />
      )}
      <DispatchWorkspaceLayout
        appointments={
          <DispatchWorkQueue
            items={visibleDispatchItems}
            jobsById={jobsById}
            loading={dispatch.isLoading}
            error={dispatch.error}
            onRetry={() => void dispatch.refetch()}
            onSelect={(item) => setSelectedAppointmentId(item.appointment_id)}
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
