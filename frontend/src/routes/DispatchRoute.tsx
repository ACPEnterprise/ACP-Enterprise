import { useState } from "react";

import { useAuth } from "../auth";
import { DispatchAppointmentsQueue, DispatchJobsQueue } from "../components/dispatch/DispatchQueues";
import { DispatchScopeControls } from "../components/dispatch/DispatchScopeControls";
import { DispatchSummary } from "../components/dispatch/DispatchSummary";
import { DispatchWorkspaceLayout } from "../components/dispatch/DispatchWorkspaceLayout";
import { dayRange, localDateValue, operationalJobStatuses } from "../components/dispatch/dispatchPresentation";
import { useJobs } from "../hooks/useJobs";
import { useAppointments } from "../hooks/useScheduling";
import { Alert } from "../ui";

export function DispatchRoute() {
  const { activeCompany } = useAuth();
  const [date, setDate] = useState(() => localDateValue(new Date()));
  const [branchId, setBranchId] = useState("");
  const [appointmentPage, setAppointmentPage] = useState(1);
  const [jobPage, setJobPage] = useState(1);
  const range = dayRange(date);
  const enabled = Boolean(activeCompany && date);
  const appointments = useAppointments({ startAt: range.startAt, endAt: range.endAt, branchId: branchId || undefined, page: appointmentPage, pageSize: 50 }, enabled);
  const jobs = useJobs({ branchId: branchId || undefined, status: operationalJobStatuses, page: jobPage, pageSize: 20, sortField: "priority", sortDirection: "desc" });
  if (!activeCompany) return <Alert variant="danger" title="Company scope unavailable">Select an accessible Company before opening Dispatch.</Alert>;
  const changeDate = (value: string) => { setDate(value); setAppointmentPage(1); };
  const changeBranch = (value: string) => { setBranchId(value); setAppointmentPage(1); setJobPage(1); };
  const appointmentTotalPages = Math.ceil((appointments.data?.total_count ?? 0) / 50);
  return <div className="min-w-0 space-y-6"><header><p className="text-sm font-medium text-action-primary">Operations</p><h2 className="mt-1 text-2xl font-bold sm:text-3xl">Dispatch</h2><p className="mt-2 text-content-muted">Review the selected day’s scheduled work and Jobs requiring operational attention.</p></header><DispatchScopeControls date={date} branchId={branchId} branches={activeCompany.branches} onDateChange={changeDate} onBranchChange={changeBranch} /><DispatchSummary appointmentTotal={appointments.data?.total_count ?? 0} jobTotal={jobs.data?.total_count ?? 0} visibleJobs={jobs.data?.items ?? []} /><DispatchWorkspaceLayout appointments={<DispatchAppointmentsQueue appointments={appointments.data?.items} loading={appointments.isLoading} error={appointments.error} onRetry={() => void appointments.refetch()} page={appointmentPage} totalPages={appointmentTotalPages} onPageChange={setAppointmentPage} />} jobs={<DispatchJobsQueue jobs={jobs.data?.items} loading={jobs.isLoading} error={jobs.error} onRetry={() => void jobs.refetch()} page={jobPage} totalPages={jobs.data?.total_pages ?? 0} onPageChange={setJobPage} />} /></div>;
}
