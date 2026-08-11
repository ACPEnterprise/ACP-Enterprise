import { useMemo, useState } from "react";
import { getOperatorApiError } from "../../api/errors";
import {
  useDispatchMutations,
  useEligibleTechnicians,
} from "../../hooks/useDispatch";
import type {
  DispatchBoardItem,
  DispatchExceptionCode,
  TechnicianEligibility,
} from "../../types/dispatch";
import {
  Alert,
  Button,
  Card,
  ConfirmationDialog,
  Select,
  Spinner,
} from "../../ui";

const label = (value: string) => value.replaceAll("_", " ");
export function DispatchAssignmentPanel({
  item,
  onClose,
}: {
  readonly item: DispatchBoardItem;
  readonly onClose: () => void;
}) {
  const technicians = useEligibleTechnicians(item.appointment_id);
  const mutations = useDispatchMutations();
  const [employeeId, setEmployeeId] = useState("");
  const [reason, setReason] = useState("Dispatcher assignment");
  const [exceptionCode, setExceptionCode] = useState<DispatchExceptionCode>(
    "assignment_ambiguous",
  );
  const [removeEmployeeId, setRemoveEmployeeId] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<
    | "assign"
    | "release"
    | "crew"
    | "crew-remove"
    | "reconcile"
    | "restore"
    | null
  >(null);
  const selected = useMemo(
    () => technicians.data?.find((x) => x.employee_id === employeeId),
    [employeeId, technicians.data],
  );
  const assignment = item.assignment;
  const pending =
    mutations.assign.isPending ||
    mutations.release.isPending ||
    mutations.crew.isPending ||
    mutations.reconcile.isPending ||
    mutations.exception.isPending;
  const error =
    mutations.assign.error ||
    mutations.release.error ||
    mutations.crew.error ||
    mutations.reconcile.error ||
    mutations.exception.error;
  const complete = () => {
    setConfirm(null);
    onClose();
  };
  const submit = () => {
    if (confirm === "release" && assignment)
      mutations.release.mutate(
        {
          appointmentId: item.appointment_id,
          version: assignment.version,
          reason,
        },
        { onSuccess: complete },
      );
    else if (confirm === "restore" && assignment)
      mutations.reconcile.mutate(
        {
          appointmentId: item.appointment_id,
          version: assignment.version,
          reason,
          resolution: "restore_assigned",
        },
        { onSuccess: complete },
      );
    else if (confirm === "reconcile" && assignment)
      mutations.exception.mutate(
        {
          appointmentId: item.appointment_id,
          version: assignment.version,
          reason,
          exceptionCode,
        },
        { onSuccess: complete },
      );
    else if (confirm === "crew-remove" && assignment && removeEmployeeId)
      mutations.crew.mutate(
        {
          appointmentId: item.appointment_id,
          employeeId: removeEmployeeId,
          version: assignment.version,
          reason,
          remove: true,
        },
        { onSuccess: complete },
      );
    else if (confirm === "crew" && assignment && employeeId)
      mutations.crew.mutate(
        {
          appointmentId: item.appointment_id,
          employeeId,
          version: assignment.version,
          reason,
        },
        { onSuccess: complete },
      );
    else if (employeeId)
      mutations.assign.mutate(
        {
          appointmentId: item.appointment_id,
          employeeId,
          reason,
          version: assignment?.version,
        },
        { onSuccess: complete },
      );
  };
  return (
    <Card
      className="space-y-4 p-ui-4"
      aria-label={`Assignment for ${item.appointment_number}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold">
            Assign {item.appointment_number}
          </h3>
          <p className="text-sm text-content-muted">
            {new Date(item.window_start_at).toLocaleString()} ·{" "}
            {assignment?.primary_employee_name ?? "No primary technician"}
          </p>
          {assignment && (
            <p className="mt-1 text-sm capitalize text-content-muted">
              Arrival: {label(assignment.arrival_state)}
            </p>
          )}
        </div>
        <Button variant="outline" onClick={onClose}>
          Close
        </Button>
      </div>
      {assignment?.status === "reconciliation_required" && (
        <div className="space-y-3">
          <Alert variant="danger" title="Reconciliation required">
            {assignment.active_exception_code
              ? `Dispatch exception: ${label(assignment.active_exception_code)}.`
              : "Assignment truth must be resolved before further changes."}
          </Alert>
          <div className="grid gap-2 sm:grid-cols-2">
            <Button onClick={() => setConfirm("restore")}>
              Confirm assignment remains active
            </Button>
            <Button variant="outline" onClick={() => setConfirm("release")}>
              Resolve as released
            </Button>
          </div>
        </div>
      )}
      {assignment &&
        assignment.status !== "reconciliation_required" &&
        assignment.status !== "released" && (
          <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
            <Select
              aria-label="Dispatch exception"
              value={exceptionCode}
              onChange={(event) =>
                setExceptionCode(event.target.value as DispatchExceptionCode)
              }
            >
              <option value="assignment_ambiguous">Assignment ambiguous</option>
              <option value="technician_unavailable">
                Technician unavailable
              </option>
              <option value="customer_unavailable">Customer unavailable</option>
              <option value="safety_condition">Safety condition</option>
              <option value="weather">Weather</option>
              <option value="other">Other</option>
            </Select>
            <Button variant="outline" onClick={() => setConfirm("reconcile")}>
              Report exception
            </Button>
          </div>
        )}
      {error && (
        <Alert variant="danger" title="Assignment not saved">
          {getOperatorApiError(error, "Dispatch").message}
        </Alert>
      )}
      {technicians.isLoading ? (
        <Spinner label="Loading eligible technicians" />
      ) : (
        <>
          <label className="block text-sm font-medium">
            Technician
            <Select
              className="mt-2"
              value={employeeId}
              onChange={(e) => setEmployeeId(e.target.value)}
            >
              <option value="">Select a technician</option>
              {technicians.data?.map((t) => (
                <option
                  key={t.employee_id}
                  value={t.employee_id}
                  disabled={!t.eligible}
                >
                  {t.display_name} —{" "}
                  {t.eligible ? "Eligible" : label(t.decision)}
                </option>
              ))}
            </Select>
          </label>
          {selected && <Eligibility item={selected} />}
          <label className="block text-sm font-medium">
            Assignment reason
            <input
              className="mt-2 min-h-11 w-full rounded-md border border-stroke bg-surface px-3"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          <div className="grid gap-2 sm:grid-cols-2">
            <Button
              disabled={
                !selected?.eligible ||
                pending ||
                assignment?.status === "reconciliation_required"
              }
              onClick={() => setConfirm("assign")}
            >
              {assignment?.primary_employee_id
                ? "Replace primary"
                : "Assign primary"}
            </Button>
            {assignment && (
              <Button
                variant="outline"
                disabled={
                  !selected?.eligible ||
                  pending ||
                  assignment.status === "reconciliation_required"
                }
                onClick={() => setConfirm("crew")}
              >
                Add crew member
              </Button>
            )}
            {assignment && (
              <Button
                variant="outline"
                disabled={pending || assignment.status === "released"}
                onClick={() => setConfirm("release")}
              >
                Release assignment
              </Button>
            )}
          </div>
          {assignment?.crew_members.length ? (
            <div>
              <h4 className="font-semibold">Crew</h4>
              <ul className="mt-2 space-y-2">
                {assignment.crew_members.map((member) => (
                  <li
                    className="flex items-center justify-between gap-3 rounded-md bg-surface-muted p-3"
                    key={member.id}
                  >
                    <span>{member.display_name}</span>
                    <Button
                      variant="outline"
                      onClick={() => {
                        setRemoveEmployeeId(member.employee_id);
                        setConfirm("crew-remove");
                      }}
                    >
                      Remove
                    </Button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <div>
            <h4 className="font-semibold">Eligibility</h4>
            <ul className="mt-2 space-y-2">
              {technicians.data?.map((t) => (
                <li
                  className="rounded-md bg-surface-muted p-3 text-sm"
                  key={t.employee_id}
                >
                  <strong>{t.display_name}</strong>
                  <span className="block text-content-muted">
                    {t.eligible ? "Eligible" : t.reasons.map(label).join(" · ")}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
      {confirm && (
        <ConfirmationDialog
          title={
            confirm === "release"
              ? "Release primary assignment?"
              : confirm === "restore"
                ? "Confirm assignment remains active?"
                : confirm === "reconcile"
                  ? "Report dispatch exception?"
                  : confirm === "crew-remove"
                    ? "Remove crew member?"
                    : confirm === "crew"
                      ? "Add crew member?"
                      : assignment
                        ? "Replace primary technician?"
                        : "Assign primary technician?"
          }
          confirmLabel="Confirm assignment change"
          pending={pending}
          onCancel={() => setConfirm(null)}
          onConfirm={submit}
        >
          <p>
            {selected?.display_name ??
              assignment?.crew_members.find(
                (x) => x.employee_id === removeEmployeeId,
              )?.display_name ??
              assignment?.primary_employee_name}{" "}
            · {item.appointment_number}
          </p>
          <p className="mt-2 text-sm text-content-muted">
            This records a durable Dispatch decision. It does not reschedule the
            Appointment.
          </p>
        </ConfirmationDialog>
      )}
    </Card>
  );
}
function Eligibility({ item }: { readonly item: TechnicianEligibility }) {
  return (
    <Alert
      variant={item.eligible ? "success" : "warning"}
      title={
        item.eligible ? "Eligible technician" : "Technician cannot be assigned"
      }
    >
      {item.eligible
        ? "Active, Branch eligible, qualified, available, and conflict-free."
        : item.reasons.map(label).join(" · ")}
    </Alert>
  );
}
