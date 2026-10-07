import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { useAuth } from "../../auth";
import { useCustomerDetail, useCustomerList } from "../../hooks/useCustomers";
import { useCreateServiceRequest } from "../../hooks/useOperations";
import { addCustomerProperty, createCustomer } from "../../api/customers";
import {
  appointmentDetailPath,
  jobDetailPath,
  schedulingReturnPath,
  withSchedulingReturn,
} from "../../routing/paths";
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
const nextOfficeSlot = (date: Date) => {
  const slot = new Date(date);
  slot.setSeconds(0, 0);
  slot.setMinutes(Math.ceil(slot.getMinutes() / 15) * 15);
  return slot;
};

export interface BookCustomerWorkContext {
  readonly branchId?: string;
  readonly startAt?: Date;
  readonly endAt?: Date;
}

export function BookCustomerWorkPanel({
  onClose,
  returnTo,
  context,
}: {
  readonly onClose: () => void;
  readonly returnTo?: string;
  readonly context?: BookCustomerWorkContext;
}) {
  const { activeCompany } = useAuth();
  const create = useCreateServiceRequest();
  const [customerSearch, setCustomerSearch] = useState("");
  const [customerMode, setCustomerMode] = useState<"existing" | "new">(
    "existing",
  );
  const [customerId, setCustomerId] = useState("");
  const customer = useCustomerDetail(customerId || null);
  const customers = useCustomerList(customerSearch, 25, 0);
  const [branchId, setBranchId] = useState(
    context?.branchId ??
      activeCompany?.default_branch_id ??
      activeCompany?.branches[0]?.id ??
      "",
  );
  const [locationId, setLocationId] = useState("");
  const [startAt, setStartAt] = useState(() =>
    localInput(
      context?.startAt ?? nextOfficeSlot(new Date(Date.now() + 60 * 60 * 1000)),
    ),
  );
  const [endAt, setEndAt] = useState(() =>
    localInput(
      context?.endAt ??
        nextOfficeSlot(new Date(Date.now() + 3 * 60 * 60 * 1000)),
    ),
  );
  const [duration, setDuration] = useState(120);
  const [priority, setPriority] = useState<JobPriority>("normal");
  const [problem, setProblem] = useState("");
  const [confirmation, setConfirmation] = useState<string | null>(null);
  const [pendingRequest, setPendingRequest] = useState<{
    fingerprint: string;
    input: ServiceRequestCreateInput;
  } | null>(null);
  const [newCustomer, setNewCustomer] = useState({
    name: "",
    phone: "",
    email: "",
    address: "",
    city: "",
    state: "",
    postalCode: "",
  });
  const [intakePending, setIntakePending] = useState(false);
  const [intakeError, setIntakeError] = useState<string | null>(null);
  const [duplicateWarnings, setDuplicateWarnings] = useState(0);
  const [createdCustomer, setCreatedCustomer] = useState<{
    id: string;
    displayName: string;
  } | null>(null);
  const confirmIntake = async () => {
    setIntakePending(true);
    setIntakeError(null);
    try {
      const [firstName, ...last] = newCustomer.name.trim().split(/\s+/);
      const created = createdCustomer
        ? null
        : await createCustomer({
            customer_type: "residential",
            first_name: firstName || null,
            last_name: last.join(" ") || null,
            business_name: null,
            primary_phone: newCustomer.phone.trim(),
            secondary_phone: null,
            email: newCustomer.email.trim() || null,
            preferred_contact_method: newCustomer.email.trim()
              ? "email"
              : "phone",
            status: "prospect",
            source: "csr_dispatch_intake",
            is_vip: false,
            internal_notes: null,
          });
      const resolvedCustomer = created
        ? {
            id: created.customer.id,
            displayName: created.customer.display_name ?? newCustomer.name,
          }
        : createdCustomer;
      if (!resolvedCustomer)
        throw new Error("Customer identity was not preserved.");
      if (created) {
        setCreatedCustomer(resolvedCustomer);
        setDuplicateWarnings(created.duplicate_warnings.length);
      }
      const location = await addCustomerProperty(resolvedCustomer.id, {
        address_line_1: newCustomer.address.trim(),
        address_line_2: null,
        city: newCustomer.city.trim(),
        state: newCustomer.state.trim(),
        postal_code: newCustomer.postalCode.trim(),
        property_type: "unknown",
        gate_access_instructions: null,
        water_shutoff_location: null,
        sewer_septic: "unknown",
        property_notes: null,
        is_primary: true,
      });
      setCustomerId(resolvedCustomer.id);
      setCustomerSearch(resolvedCustomer.displayName);
      setLocationId(location.id);
      setCreatedCustomer(null);
      setCustomerMode("existing");
    } catch (error) {
      setIntakeError(
        error instanceof Error ? error.message : "Customer intake failed.",
      );
    } finally {
      setIntakePending(false);
    }
  };

  const selectedCustomer = customers.data?.items.find(
    (item) => item.id === customerId,
  );
  const resolvedLocationId =
    locationId ||
    (customer.data?.properties.length === 1
      ? customer.data.properties[0].id
      : "");
  const selectedLocation = customer.data?.properties.find(
    (item) => item.id === resolvedLocationId,
  );
  const start = new Date(startAt);
  const end = new Date(endAt);
  const validWindow =
    !Number.isNaN(start.getTime()) &&
    !Number.isNaN(end.getTime()) &&
    end > start;
  const officeSlotValid =
    [start, end].every(
      (value) =>
        !Number.isNaN(value.getTime()) && value.getMinutes() % 15 === 0,
    ) &&
    duration >= 15 &&
    duration % 15 === 0;
  const ready = Boolean(
    branchId &&
    customerId &&
    resolvedLocationId &&
    startAt &&
    endAt &&
    validWindow &&
    officeSlotValid,
  );
  const error = create.error
    ? schedulingMutationRecovery(create.error, "booking")
    : null;

  const review = (event: FormEvent) => {
    event.preventDefault();
    if (!ready) return;
    const intent = {
      branch_id: branchId,
      customer_id: customerId,
      service_location_id: resolvedLocationId,
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
    const input =
      pendingRequest?.fingerprint === fingerprint
        ? pendingRequest.input
        : { ...intent, request_id: crypto.randomUUID() };
    setPendingRequest({ fingerprint, input });
    setConfirmation(input.request_id);
  };
  const confirm = () => {
    if (!confirmation || !pendingRequest) return;
    create.mutate(pendingRequest.input, {
      onSuccess: () => {
        setConfirmation(null);
        setPendingRequest(null);
      },
      onError: () => setConfirmation(null),
    });
  };

  return (
    <section
      className="rounded-xl border border-stroke bg-surface p-4 sm:p-6"
      aria-labelledby="book-customer-work-heading"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm text-action-primary">CSR scheduling</p>
          <h2 id="book-customer-work-heading" className="text-xl font-semibold">
            Book customer work
          </h2>
          <p className="mt-1 text-sm text-content-muted">
            Create one Appointment and its related draft Job through the
            authoritative service-request workflow.
          </p>
        </div>
        <Button variant="ghost" onClick={onClose}>
          Close
        </Button>
      </div>
      {error && (
        <Alert
          className="mt-4"
          variant="danger"
          title={error.title}
          action={
            error.retryLabel && pendingRequest ? (
              <Button
                variant="outline"
                onClick={() => setConfirmation(pendingRequest.input.request_id)}
                disabled={create.isPending}
              >
                {error.retryLabel}
              </Button>
            ) : undefined
          }
        >
          <strong>{error.state.replaceAll("_", " ")}</strong> — {error.message}
        </Alert>
      )}
      {create.data && (
        <Alert className="mt-4" variant="success" title="Work booked">
          SUCCEEDED — {create.data.appointment.appointment_number} and{" "}
          {create.data.job.job_number} were saved and authoritative
          queue/calendar state was refreshed. Assignment remains a separate
          human-confirmed Dispatch action.
          <div className="mt-3 flex flex-wrap gap-3">
            <Link
              className="font-semibold text-action-primary underline"
              to={
                returnTo
                  ? withSchedulingReturn(
                      appointmentDetailPath(create.data.appointment.id),
                      returnTo,
                    )
                  : appointmentDetailPath(create.data.appointment.id)
              }
            >
              Open Appointment
            </Link>
            <Link
              className="font-semibold text-action-primary underline"
              to={
                returnTo
                  ? withSchedulingReturn(
                      jobDetailPath(create.data.job.id),
                      returnTo,
                    )
                  : jobDetailPath(create.data.job.id)
              }
            >
              Open Job
            </Link>
            <Link
              className="font-semibold text-action-primary underline"
              to="/dispatch"
            >
              Assign in Dispatch
            </Link>
            {returnTo ? (
              <Link
                className="font-semibold text-action-primary underline"
                to={schedulingReturnPath(returnTo)}
              >
                Return to prior Schedule view
              </Link>
            ) : null}
          </div>
        </Alert>
      )}
      <form className="mt-5 grid gap-4 md:grid-cols-2" onSubmit={review}>
        <div
          className="flex gap-2 md:col-span-2"
          aria-label="Customer resolution state"
        >
          <Button
            type="button"
            variant={customerMode === "existing" ? "primary" : "outline"}
            onClick={() => setCustomerMode("existing")}
          >
            Existing Customer
          </Button>
          <Button
            type="button"
            variant={customerMode === "new" ? "primary" : "outline"}
            onClick={() => setCustomerMode("new")}
          >
            New Customer intake
          </Button>
        </div>
        {customerMode === "new" && (
          <section
            className="grid gap-4 rounded-lg border border-stroke bg-surface-subtle p-4 md:col-span-2 md:grid-cols-2"
            aria-label="Compact Customer intake"
          >
            <Alert className="md:col-span-2" title="Confirmation required">
              No Customer or Location is created until you select Confirm
              Customer and Location.
            </Alert>
            <Field label="Customer name" required>
              <Input
                value={newCustomer.name}
                onChange={(event) =>
                  setNewCustomer((value) => ({
                    ...value,
                    name: event.target.value,
                  }))
                }
              />
            </Field>
            <Field label="Phone" required>
              <Input
                type="tel"
                value={newCustomer.phone}
                onChange={(event) =>
                  setNewCustomer((value) => ({
                    ...value,
                    phone: event.target.value,
                  }))
                }
              />
            </Field>
            <Field label="Email">
              <Input
                type="email"
                value={newCustomer.email}
                onChange={(event) =>
                  setNewCustomer((value) => ({
                    ...value,
                    email: event.target.value,
                  }))
                }
              />
            </Field>
            <Field label="Service address" required>
              <Input
                value={newCustomer.address}
                onChange={(event) =>
                  setNewCustomer((value) => ({
                    ...value,
                    address: event.target.value,
                  }))
                }
              />
            </Field>
            <Field label="City" required>
              <Input
                value={newCustomer.city}
                onChange={(event) =>
                  setNewCustomer((value) => ({
                    ...value,
                    city: event.target.value,
                  }))
                }
              />
            </Field>
            <Field label="State" required>
              <Input
                value={newCustomer.state}
                onChange={(event) =>
                  setNewCustomer((value) => ({
                    ...value,
                    state: event.target.value,
                  }))
                }
              />
            </Field>
            <Field label="Postal code" required>
              <Input
                value={newCustomer.postalCode}
                onChange={(event) =>
                  setNewCustomer((value) => ({
                    ...value,
                    postalCode: event.target.value,
                  }))
                }
              />
            </Field>
            <div className="flex items-end">
              <Button
                type="button"
                disabled={
                  intakePending ||
                  !newCustomer.name.trim() ||
                  !newCustomer.phone.trim() ||
                  !newCustomer.address.trim() ||
                  !newCustomer.city.trim() ||
                  !newCustomer.state.trim() ||
                  !newCustomer.postalCode.trim()
                }
                onClick={() => void confirmIntake()}
              >
                Confirm Customer and Location
              </Button>
            </div>
            {intakeError && (
              <Alert
                className="md:col-span-2"
                variant="danger"
                title="Customer intake not saved"
              >
                {intakeError}
              </Alert>
            )}
            {duplicateWarnings > 0 ? (
              <Alert
                className="md:col-span-2"
                variant="warning"
                title="Potential duplicate Customer"
              >
                Review the existing Customer matches before proceeding. The
                authoritative Customer response preserved the duplicate warning.
              </Alert>
            ) : null}
          </section>
        )}
        {customerMode === "existing" && (
          <>
            <Field
              label="Find Customer"
              helperText={
                customers.isError
                  ? "Customer search is unavailable."
                  : "Search is bounded to 25 authorized Customers."
              }
            >
              <Input
                value={customerSearch}
                onChange={(event) => setCustomerSearch(event.target.value)}
                placeholder="Name or customer number"
              />
            </Field>
            <Field label="Customer" required>
              <Select
                value={customerId}
                onChange={(event) => {
                  setCustomerId(event.target.value);
                  setLocationId("");
                }}
                required
              >
                <option value="">Select Customer</option>
                {(customers.data?.items ?? []).map((item) => (
                  <option value={item.id} key={item.id}>
                    {item.business_name ||
                      `${item.first_name ?? ""} ${item.last_name ?? ""}`.trim()}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              label="Service Location"
              required
              helperText={
                customerId && customer.data?.properties.length === 0
                  ? "This Customer has no authorized Service Locations."
                  : undefined
              }
            >
              <Select
                value={resolvedLocationId}
                onChange={(event) => setLocationId(event.target.value)}
                disabled={!customerId || customer.isLoading}
                required
              >
                <option value="">Select Service Location</option>
                {(customer.data?.properties ?? []).map((item) => (
                  <option value={item.id} key={item.id}>
                    {item.address_line_1}, {item.city}
                  </option>
                ))}
              </Select>
            </Field>
          </>
        )}
        <Field label="Branch" required>
          <Select
            value={branchId}
            onChange={(event) => setBranchId(event.target.value)}
            required
          >
            <option value="">Select Branch</option>
            {(activeCompany?.branches ?? []).map((item) => (
              <option value={item.id} key={item.id}>
                {item.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field
          label="Arrival window starts"
          required
          helperText="Choose a 15-minute office slot."
        >
          <Input
            type="datetime-local"
            step={900}
            value={startAt}
            onChange={(event) => setStartAt(event.target.value)}
            required
          />
        </Field>
        <Field
          label="Arrival window ends"
          required
          helperText={
            startAt && endAt && !validWindow
              ? "Arrival window must end after it starts."
              : "Customer-facing arrival window in 15-minute increments; this is separate from expected work duration."
          }
        >
          <Input
            type="datetime-local"
            step={900}
            value={endAt}
            onChange={(event) => setEndAt(event.target.value)}
            min={startAt || undefined}
            required
          />
        </Field>
        <Field label="Expected duration (minutes)" required>
          <Input
            type="number"
            min={15}
            max={1440}
            step={15}
            value={duration}
            onChange={(event) => setDuration(Number(event.target.value))}
            required
          />
        </Field>
        {!officeSlotValid ? (
          <p className="text-sm text-status-danger md:col-span-2">
            Choose :00, :15, :30, or :45 and use a 15-minute duration increment.
          </p>
        ) : null}
        <Field label="Priority">
          <Select
            value={priority}
            onChange={(event) => setPriority(event.target.value as JobPriority)}
          >
            {["low", "normal", "high", "urgent", "emergency"].map((value) => (
              <option value={value} key={value}>
                {value}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Customer-reported problem" className="md:col-span-2">
          <Textarea
            value={problem}
            onChange={(event) => setProblem(event.target.value)}
          />
        </Field>
        <div className="flex flex-wrap justify-end gap-2 md:col-span-2">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={!ready || create.isPending}>
            Review booking
          </Button>
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
