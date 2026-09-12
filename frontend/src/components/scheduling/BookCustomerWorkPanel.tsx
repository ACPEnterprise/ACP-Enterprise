import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { useAuth } from "../../auth";
import { useCustomerDetail, useCustomerList } from "../../hooks/useCustomers";
import { useCreateServiceRequest } from "../../hooks/useOperations";
import { appointmentDetailPath, jobDetailPath, schedulingReturnPath, withSchedulingReturn } from "../../routing/paths";
import type { JobPriority } from "../../types/jobs";
import type { ServiceRequestCreateInput } from "../../types/operations";
import { schedulingMutationRecovery } from "./schedulingRecovery";
import {
  Alert,
  Button,
  ConfirmationDialog,
  Field,
  Input,
  Select,
  Textarea,
} from "../../ui";

const localInput = (date: Date) => {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

export function BookCustomerWorkPanel({ onClose, returnTo }: { readonly onClose: () => void; readonly returnTo?: string }) {
  const { activeCompany } = useAuth();
  const create = useCreateServiceRequest();
  const [customerSearch, setCustomerSearch] = useState("");
  const [customerId, setCustomerId] = useState("");
  const customer = useCustomerDetail(customerId || null);
  const customers = useCustomerList(customerSearch, 25, 0);
  const [branchId, setBranchId] = useState(
    activeCompany?.default_branch_id ?? activeCompany?.branches[0]?.id ?? "",
  );
  const [locationId, setLocationId] = useState("");
  const [startAt, setStartAt] = useState(() => localInput(new Date(Date.now() + 60 * 60 * 1000)));
  const [endAt, setEndAt] = useState(() => localInput(new Date(Date.now() + 3 * 60 * 60 * 1000)));
  const [duration, setDuration] = useState(120);
  const [priority, setPriority] = useState<JobPriority>("normal");
  const [problem, setProblem] = useState("");
  const [confirmation, setConfirmation] = useState<string | null>(null);
  const [pendingRequest, setPendingRequest] = useState<{ fingerprint: string; input: ServiceRequestCreateInput } | null>(null);

  const selectedCustomer = customers.data?.items.find((item) => item.id === customerId);
  const selectedLocation = customer.data?.properties.find((item) => item.id === locationId);
  const start = new Date(startAt);
  const end = new Date(endAt);
  const validWindow = !Number.isNaN(start.getTime()) && !Number.isNaN(end.getTime()) && end > start;
  const ready = Boolean(
    branchId && customerId && locationId && startAt && endAt && duration > 0 && validWindow,
  );
  const error = create.error ? schedulingMutationRecovery(create.error, "booking") : null;

  const review = (event: FormEvent) => {
    event.preventDefault();
    if (!ready) return;
    const intent = {
      branch_id: branchId,
      customer_id: customerId,
      service_location_id: locationId,
      arrival_window_start_at: start.toISOString(),
      arrival_window_end_at: end.toISOString(),
      expected_duration_minutes: duration,
      capacity_units: "1.00",
      job_type_code: null,
      priority,
      customer_reported_problem: problem.trim() || null,
      internal_description: null,
    } satisfies Omit<ServiceRequestCreateInput, "request_id">;
    const fingerprint = JSON.stringify(intent);
    const input = pendingRequest?.fingerprint === fingerprint
      ? pendingRequest.input
      : { ...intent, request_id: crypto.randomUUID() };
    setPendingRequest({ fingerprint, input });
    setConfirmation(input.request_id);
  };
  const confirm = () => {
    if (!confirmation || !pendingRequest) return;
    create.mutate(pendingRequest.input, {
      onSuccess: () => { setConfirmation(null); setPendingRequest(null); },
      onError: () => setConfirmation(null),
    });
  };

  return (
    <section className="rounded-xl border border-stroke bg-surface p-4 sm:p-6" aria-labelledby="book-customer-work-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm text-action-primary">CSR scheduling</p>
          <h2 id="book-customer-work-heading" className="text-xl font-semibold">Book customer work</h2>
          <p className="mt-1 text-sm text-content-muted">Create one Appointment and its related draft Job through the authoritative service-request workflow.</p>
        </div>
        <Button variant="ghost" onClick={onClose}>Close</Button>
      </div>
      {error && <Alert className="mt-4" variant="danger" title={error.title} action={error.retryLabel && pendingRequest ? <Button variant="outline" onClick={() => setConfirmation(pendingRequest.input.request_id)} disabled={create.isPending}>{error.retryLabel}</Button> : undefined}><strong>{error.state.replaceAll("_", " ")}</strong> — {error.message}</Alert>}
      {create.data && (
        <Alert className="mt-4" variant="success" title="Work booked">
          SUCCEEDED — {create.data.appointment.appointment_number} and {create.data.job.job_number} were saved and authoritative queue/calendar state was refreshed. Assignment remains a separate human-confirmed Dispatch action.
          <div className="mt-3 flex flex-wrap gap-3">
            <Link className="font-semibold text-action-primary underline" to={returnTo ? withSchedulingReturn(appointmentDetailPath(create.data.appointment.id), returnTo) : appointmentDetailPath(create.data.appointment.id)}>Open Appointment</Link>
            <Link className="font-semibold text-action-primary underline" to={returnTo ? withSchedulingReturn(jobDetailPath(create.data.job.id), returnTo) : jobDetailPath(create.data.job.id)}>Open Job</Link>
            <Link className="font-semibold text-action-primary underline" to="/dispatch">Assign in Dispatch</Link>
            {returnTo ? <Link className="font-semibold text-action-primary underline" to={schedulingReturnPath(returnTo)}>Return to prior Schedule view</Link> : null}
          </div>
        </Alert>
      )}
      <form className="mt-5 grid gap-4 md:grid-cols-2" onSubmit={review}>
        <Field label="Find Customer" helperText={customers.isError ? "Customer search is unavailable." : "Search is bounded to 25 authorized Customers."}>
          <Input value={customerSearch} onChange={(event) => setCustomerSearch(event.target.value)} placeholder="Name or customer number" />
        </Field>
        <Field label="Customer" required>
          <Select value={customerId} onChange={(event) => { setCustomerId(event.target.value); setLocationId(""); }} required>
            <option value="">Select Customer</option>
            {(customers.data?.items ?? []).map((item) => <option value={item.id} key={item.id}>{item.business_name || `${item.first_name ?? ""} ${item.last_name ?? ""}`.trim()}</option>)}
          </Select>
        </Field>
        <Field label="Service Location" required helperText={customerId && customer.data?.properties.length === 0 ? "This Customer has no authorized Service Locations." : undefined}>
          <Select value={locationId} onChange={(event) => setLocationId(event.target.value)} disabled={!customerId || customer.isLoading} required>
            <option value="">Select Service Location</option>
            {(customer.data?.properties ?? []).map((item) => <option value={item.id} key={item.id}>{item.address_line_1}, {item.city}</option>)}
          </Select>
        </Field>
        <Field label="Branch" required>
          <Select value={branchId} onChange={(event) => setBranchId(event.target.value)} required>
            <option value="">Select Branch</option>
            {(activeCompany?.branches ?? []).map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}
          </Select>
        </Field>
        <Field label="Arrival window starts" required><Input type="datetime-local" value={startAt} onChange={(event) => setStartAt(event.target.value)} required /></Field>
        <Field label="Arrival window ends" required helperText={startAt && endAt && !validWindow ? "Arrival window must end after it starts." : "Customer-facing arrival window; this is separate from expected work duration."}><Input type="datetime-local" value={endAt} onChange={(event) => setEndAt(event.target.value)} min={startAt || undefined} required /></Field>
        <Field label="Expected duration (minutes)" required><Input type="number" min={15} max={1440} value={duration} onChange={(event) => setDuration(Number(event.target.value))} required /></Field>
        <Field label="Priority"><Select value={priority} onChange={(event) => setPriority(event.target.value as JobPriority)}>{["low", "normal", "high", "urgent", "emergency"].map((value) => <option value={value} key={value}>{value}</option>)}</Select></Field>
        <Field label="Customer-reported problem" className="md:col-span-2"><Textarea value={problem} onChange={(event) => setProblem(event.target.value)} /></Field>
        <div className="flex flex-wrap justify-end gap-2 md:col-span-2">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={!ready || create.isPending}>Review booking</Button>
        </div>
      </form>
      {confirmation && (
        <ConfirmationDialog
          title="Book this customer work?"
          description={`${selectedCustomer?.business_name || `${selectedCustomer?.first_name ?? ""} ${selectedCustomer?.last_name ?? ""}`.trim() || "Selected Customer"} · ${selectedLocation?.address_line_1 ?? "Selected Location"} · ${start.toLocaleString()}–${end.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}. No technician will be assigned automatically.`}
          confirmLabel="Confirm booking"
          pending={create.isPending}
          onConfirm={confirm}
          onCancel={() => setConfirmation(null)}
        />
      )}
    </section>
  );
}
