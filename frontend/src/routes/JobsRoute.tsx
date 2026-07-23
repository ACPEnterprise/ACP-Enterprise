import { useState, type FormEvent } from "react";
import { ChevronLeft, ChevronRight, Plus, Search } from "lucide-react";

import { JobsEmptyState, JobsErrorState, JobsLoadingState } from "../components/jobs/JobStates";
import { JobsTable } from "../components/jobs/JobsTable";
import { CreateJobPanel } from "../components/jobs/CreateJobPanel";
import { useAuth } from "../auth";
import { useJobs } from "../hooks/useJobs";
import type { JobPriority, JobSortField, JobStatus, SortDirection } from "../types/jobs";
import { Button, Input, Select } from "../ui";

export function JobsRoute() {
  const { activeCompany } = useAuth();
  const [creating, setCreating] = useState(false);
  const [input, setInput] = useState(""); const [searchText, setSearchText] = useState("");
  const [status, setStatus] = useState<JobStatus | "">(""); const [priority, setPriority] = useState<JobPriority | "">("");
  const [jobType, setJobType] = useState(""); const [branchId, setBranchId] = useState("");
  const [sortField, setSortField] = useState<JobSortField>("updated_at"); const [sortDirection, setSortDirection] = useState<SortDirection>("desc"); const [page, setPage] = useState(1);
  const query = useJobs({ searchText, status: status ? [status] : undefined, priority: priority ? [priority] : undefined, jobType: jobType ? [jobType] : undefined, branchId: branchId || undefined, page, pageSize: 20, sortField, sortDirection });
  const submit = (event: FormEvent) => { event.preventDefault(); setPage(1); setSearchText(input.trim()); };
  return <div className="space-y-6"><header className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-sm font-medium text-blue-400">Operations</p><h2 className="mt-1 text-3xl font-bold">Jobs</h2><p className="mt-2 text-slate-400">Manage work from creation through completion.</p></div><Button leadingIcon={<Plus size={18} />} onClick={() => setCreating(true)}>Create Job</Button></header>
    {creating && <CreateJobPanel onCancel={() => setCreating(false)} />}
    <form onSubmit={submit} className="grid gap-3 rounded-xl border border-stroke bg-surface p-ui-4 md:grid-cols-4">
      <label className="relative md:col-span-2"><span className="sr-only">Search Jobs</span><Search className="absolute left-3 top-3 text-slate-500" size={18} /><Input className="pl-10" value={input} onChange={(event) => setInput(event.target.value)} placeholder="Job number, customer, location, or problem" /></label>
      <Select aria-label="Job status" value={status} onChange={(event) => { setStatus(event.target.value as JobStatus | ""); setPage(1); }}><option value="">All statuses</option>{["draft", "ready", "in_progress", "paused", "completed", "cancelled"].map((value) => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</Select>
      <Select aria-label="Job priority" value={priority} onChange={(event) => { setPriority(event.target.value as JobPriority | ""); setPage(1); }}><option value="">All priorities</option>{["low", "normal", "high", "urgent", "emergency"].map((value) => <option key={value}>{value}</option>)}</Select>
      <Input aria-label="Job type" value={jobType} onChange={(event) => { setJobType(event.target.value); setPage(1); }} placeholder="Job type code" />
      <Select aria-label="Branch" value={branchId} onChange={(event) => { setBranchId(event.target.value); setPage(1); }}><option value="">All accessible Branches</option>{activeCompany?.branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name}</option>)}</Select>
      <Select aria-label="Sort Jobs" value={sortField} onChange={(event) => setSortField(event.target.value as JobSortField)}><option value="updated_at">Recently updated</option><option value="job_number">Job number</option><option value="priority">Priority</option><option value="status">Status</option><option value="earliest_appointment_start_at">Appointment time</option></Select>
      <div className="flex gap-2"><Select aria-label="Sort direction" value={sortDirection} onChange={(event) => setSortDirection(event.target.value as SortDirection)}><option value="desc">Descending</option><option value="asc">Ascending</option></Select><Button type="submit">Search</Button></div>
    </form>
    <section className="rounded-xl border border-stroke bg-surface">{query.isLoading && <JobsLoadingState />}{query.isError && <div className="p-ui-5"><JobsErrorState error={query.error} onRetry={() => void query.refetch()} /></div>}{query.data?.items.length === 0 && <div className="p-ui-5"><JobsEmptyState /></div>}{query.data && query.data.items.length > 0 && <JobsTable jobs={query.data.items} />}{query.data && query.data.total_pages > 0 && <footer className="flex items-center justify-between border-t border-stroke p-ui-4 text-sm text-content-muted"><span>Page {query.data.page} of {query.data.total_pages} · {query.data.total_count} Jobs</span><div className="flex gap-2"><Button variant="outline" aria-label="Previous page" disabled={page === 1} onClick={() => setPage((value) => value - 1)}><ChevronLeft size={17} /></Button><Button variant="outline" aria-label="Next page" disabled={page >= query.data.total_pages} onClick={() => setPage((value) => value + 1)}><ChevronRight size={17} /></Button></div></footer>}</section>
  </div>;
}
