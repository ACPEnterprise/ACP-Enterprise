import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";

import { getOperatorApiError } from "../../api/errors";
import { useAuth } from "../../auth";
import { useCustomerDetail, useCustomerSearch } from "../../hooks/useCustomers";
import { useCreateJob } from "../../hooks/useJobs";
import type { JobPriority } from "../../types/jobs";
import { Alert, Button, Field, Input, Select, Textarea } from "../../ui";

export function CreateJobPanel({ onCancel, initialCustomerId = "", initialLocationId = "" }: { readonly onCancel: () => void; readonly initialCustomerId?: string; readonly initialLocationId?: string }) {
  const navigate = useNavigate(); const { activeCompany } = useAuth(); const create = useCreateJob();
  const [customerSearchInput, setCustomerSearchInput] = useState(""); const [customerSearch, setCustomerSearch] = useState(""); const [customerPage, setCustomerPage] = useState(1);
  const customers = useCustomerSearch({ query: customerSearch || undefined, sort_by: "display_name", sort_direction: "asc", page: customerPage, page_size: 25 }); const [customerId, setCustomerId] = useState(initialCustomerId);
  const customer = useCustomerDetail(customerId || null); const [branchId, setBranchId] = useState(activeCompany?.default_branch_id ?? activeCompany?.branches[0]?.id ?? "");
  const [locationId, setLocationId] = useState(initialLocationId); const [jobType, setJobType] = useState("");
  const [priority, setPriority] = useState<JobPriority>("normal"); const [problem, setProblem] = useState(""); const [description, setDescription] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!branchId || !customerId || !locationId) return;
    create.mutate({ branch_id: branchId, customer_id: customerId, service_location_id: locationId, job_type_code: jobType.trim() || null, priority, customer_reported_problem: problem.trim() || null, internal_description: description.trim() || null }, { onSuccess: (job) => void navigate(`/jobs/${job.id}`) });
  };
  const error = create.error ? getOperatorApiError(create.error) : null;
  return <section className="rounded-xl border border-stroke bg-surface p-ui-6" aria-labelledby="create-job-heading">
    <div className="flex items-start justify-between"><div><h3 id="create-job-heading" className="text-xl font-semibold">Create Job</h3><p className="mt-1 text-sm text-content-muted">Create a draft Job from an existing Customer and Service Location.</p></div><Button variant="ghost" onClick={onCancel}>Close</Button></div>
    {error && <Alert className="mt-4" variant="danger" title={error.title}>{error.message}</Alert>}
    <form className="mt-5 grid gap-4 md:grid-cols-2" onSubmit={submit}>
      <Field label="Branch" required><Select value={branchId} onChange={(event) => setBranchId(event.target.value)} required><option value="">Select Branch</option>{activeCompany?.branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name} ({branch.code})</option>)}</Select></Field>
      <Field label="Find Customer" helperText="Searches the admitted roster; held Migration records are not selectable."><div className="grid gap-2 sm:grid-cols-[1fr_auto]"><Input aria-label="Find Customer" value={customerSearchInput} onChange={(event) => setCustomerSearchInput(event.target.value)} placeholder="Name, number, phone, email, or address" /><Button type="button" variant="outline" onClick={() => { setCustomerSearch(customerSearchInput.trim()); setCustomerPage(1); }}>Search</Button></div></Field>
      <Field label="Customer" required helperText={customers.isError ? "Customer search is unavailable; no selection was changed." : customers.data ? `Showing ${customers.data.items.length} of ${customers.data.total_count} admitted Customers · page ${customers.data.page} of ${customers.data.total_pages || 1}` : undefined}><Select value={customerId} onChange={(event) => { setCustomerId(event.target.value); setLocationId(""); }} required disabled={customers.isLoading}><option value="">Select Customer</option>{customer.data && !customers.data?.items.some((item) => item.id === customer.data.id) && <option value={customer.data.id}>{customer.data.display_name || customer.data.business_name || "Selected Customer"}</option>}{customers.data?.items.map((item) => <option key={item.id} value={item.id}>{item.display_name || item.business_name || `${item.first_name ?? ""} ${item.last_name ?? ""}`.trim()}</option>)}</Select><div className="mt-2 flex gap-2"><Button type="button" variant="ghost" disabled={!customers.data || customerPage <= 1} onClick={() => setCustomerPage((value) => Math.max(1, value - 1))}>Previous Customers</Button><Button type="button" variant="ghost" disabled={!customers.data || customerPage >= customers.data.total_pages} onClick={() => setCustomerPage((value) => value + 1)}>Next Customers</Button></div></Field>
      <Field label="Service Location" required helperText={customerId && customer.data?.properties.length === 0 ? "This Customer has no Service Locations." : undefined}><Select value={locationId} onChange={(event) => setLocationId(event.target.value)} required disabled={!customerId || customer.isLoading}><option value="">Select Service Location</option>{customer.data?.properties.map((location) => <option key={location.id} value={location.id}>{location.address_line_1}, {location.city}</option>)}</Select></Field>
      <Field label="Priority"><Select value={priority} onChange={(event) => setPriority(event.target.value as JobPriority)}>{["low", "normal", "high", "urgent", "emergency"].map((value) => <option key={value} value={value}>{value}</option>)}</Select></Field>
      <Field label="Job type code" helperText="Optional operational code, such as repair or maintenance."><Input value={jobType} maxLength={64} pattern="[a-z][a-z0-9_]*" onChange={(event) => setJobType(event.target.value)} /></Field>
      <Field label="Customer-reported problem" className="md:col-span-2"><Textarea value={problem} onChange={(event) => setProblem(event.target.value)} /></Field>
      <Field label="Internal description" className="md:col-span-2"><Textarea value={description} onChange={(event) => setDescription(event.target.value)} /></Field>
      <div className="flex justify-end gap-2 md:col-span-2"><Button variant="outline" onClick={onCancel}>Cancel</Button><Button type="submit" loading={create.isPending} loadingLabel="Creating Job" disabled={!branchId || !customerId || !locationId}>Create Job</Button></div>
    </form>
  </section>;
}
