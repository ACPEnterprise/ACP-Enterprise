import { useState, type FormEvent } from "react";
import type {
  DecidePurchaseOrderChange,
  PurchaseOrder,
  PurchaseOrderChangeOperation,
  PurchaseOrderChangeOperationName,
  RequestPurchaseOrderChange,
} from "../types/purchasing";
import { Alert, Badge, Button, Input, Select } from "../ui";

interface Props {
  po: PurchaseOrder;
  canRequest: boolean;
  canApprove: boolean;
  requestPending: boolean;
  decisionPending: boolean;
  errorMessage: string | null;
  onRequest: (input: RequestPurchaseOrderChange) => Promise<unknown>;
  onDecision: (
    changeId: string,
    action: "approve" | "reject",
    input: DecidePurchaseOrderChange,
  ) => Promise<unknown>;
}

const operationLabel: Record<PurchaseOrderChangeOperationName, string> = {
  set_quantity: "Change ordered quantity",
  set_unit_cost: "Change unit price",
  cancel_line: "Cancel unreceived line",
  add_line: "Add order line",
  set_expected_date: "Change expected date",
};

function safeSnapshotSummary(snapshot: Record<string, unknown>): string {
  const lines = Array.isArray(snapshot.lines) ? snapshot.lines.length : 0;
  const expected = typeof snapshot.expected_date === "string" ? snapshot.expected_date : "not set";
  return `${lines} line${lines === 1 ? "" : "s"}; expected ${expected}`;
}

export function PurchaseOrderChangeControls({
  po,
  canRequest,
  canApprove,
  requestPending,
  decisionPending,
  errorMessage,
  onRequest,
  onDecision,
}: Props) {
  const [open, setOpen] = useState(false);
  const [operation, setOperation] = useState<PurchaseOrderChangeOperationName>("set_quantity");
  const [lineId, setLineId] = useState(po.lines[0]?.id ?? "");
  const [value, setValue] = useState("");
  const [description, setDescription] = useState("");
  const [unit, setUnit] = useState("each");
  const [reason, setReason] = useState("");
  const line = po.lines.find((item) => item.id === lineId);

  const proposed = (): PurchaseOrderChangeOperation => {
    if (operation === "set_expected_date") return { operation, expected_date: value || null };
    if (operation === "add_line")
      return { operation, description, quantity: value, unit, unit_cost: "0" };
    if (operation === "cancel_line") return { operation, line_id: lineId };
    return {
      operation,
      line_id: lineId,
      ...(operation === "set_quantity" ? { quantity: value } : { unit_cost: value }),
    };
  };
  const currentValue =
    operation === "set_expected_date"
      ? po.expected_date ?? "not set"
      : operation === "add_line"
        ? "No line"
        : operation === "cancel_line"
          ? line?.is_cancelled ? "Canceled" : "Active"
          : operation === "set_quantity"
            ? line?.quantity ?? "Select a line"
            : line?.unit_cost ?? "Select a line";
  const proposedValue =
    operation === "cancel_line" ? "Canceled" : operation === "add_line" ? `${value} ${unit} ${description}` : value;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    await onRequest({
      expected_po_version: po.version,
      base_revision: po.effective_revision,
      change_identity: crypto.randomUUID(),
      reason,
      changes: [proposed()],
      idempotency_key: crypto.randomUUID(),
    });
    setOpen(false);
    setReason("");
    setValue("");
  };

  return (
    <section className="mt-4 rounded border border-stroke p-3" aria-label={`Change orders for ${po.po_number}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <strong>Change-order controls</strong>
          <p className="text-sm text-content-muted">Current effective revision V{po.effective_revision}. Proposed changes are not effective until approved.</p>
        </div>
        {canRequest && po.status === "issued" && <Button onClick={() => setOpen(!open)}>Request PO change</Button>}
      </div>
      {errorMessage && <Alert variant="danger">{errorMessage}</Alert>}
      {open && (
        <form className="mt-3 grid gap-3 sm:grid-cols-2" onSubmit={(event) => void submit(event)}>
          <Select aria-label="Change type" value={operation} onChange={(event) => setOperation(event.target.value as PurchaseOrderChangeOperationName)}>
            {Object.entries(operationLabel).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </Select>
          {!['add_line', 'set_expected_date'].includes(operation) && (
            <Select aria-label="Change order line" required value={lineId} onChange={(event) => setLineId(event.target.value)}>
              {po.lines.map((item) => <option key={item.id} value={item.id}>Line {item.line_number}: {item.description}</option>)}
            </Select>
          )}
          {operation === "add_line" && <><Input aria-label="New line description" required value={description} onChange={(event) => setDescription(event.target.value)} /><Input aria-label="New line unit" required value={unit} onChange={(event) => setUnit(event.target.value)} /></>}
          {operation !== "cancel_line" && <Input aria-label="Proposed value" required type={operation === "set_expected_date" ? "date" : "number"} min={operation === "set_expected_date" ? undefined : "0.000001"} step={operation === "set_expected_date" ? undefined : "0.000001"} value={value} onChange={(event) => setValue(event.target.value)} />}
          <Input aria-label="Change reason" required value={reason} onChange={(event) => setReason(event.target.value)} />
          <div className="rounded bg-surface-muted p-3 text-sm sm:col-span-2">
            <div><strong>Current authoritative value:</strong> {currentValue}</div>
            <div><strong>Proposed value:</strong> {proposedValue || "Enter a value"}</div>
            {line && <div className="text-content-muted">Received {line.cumulative_accepted_quantity}; remaining {line.outstanding_quantity}. Server authority enforces the minimum permitted quantity and cancellation rules.</div>}
          </div>
          <Button type="submit" loading={requestPending}>Submit change request</Button>
        </form>
      )}
      <div className="mt-3 space-y-2">
        {po.change_orders.map((change) => (
          <div key={change.id} className="rounded border border-stroke p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2"><strong>From V{change.base_revision}</strong><Badge>{change.status}</Badge>{change.effective_revision && <span>Effective as V{change.effective_revision}</span>}</div>
            <div>Reason: {change.reason}</div>
            <div>Requested {new Date(change.requested_at).toLocaleString()} by user {change.requested_by_user_id}</div>
            {change.proposed_changes.map((item, index) => <div key={`${change.id}-${index}`}>{operationLabel[item.operation]}: {JSON.stringify(item)}</div>)}
            {change.downstream_reconciliation_required && <Alert variant="warning">Downstream financial reconciliation is required. No AP or Accounting effect was created.</Alert>}
            {change.status === "requested" && canApprove && (
              <div className="mt-2 flex gap-2"><Button loading={decisionPending} onClick={() => void onDecision(change.id, "approve", { expected_po_version: po.version, expected_base_revision: po.effective_revision, idempotency_key: crypto.randomUUID() })}>Approve change</Button><Button loading={decisionPending} onClick={() => void onDecision(change.id, "reject", { expected_po_version: po.version, expected_base_revision: po.effective_revision, reason: "Rejected by authorized Purchasing reviewer", idempotency_key: crypto.randomUUID() })}>Reject change</Button></div>
            )}
          </div>
        ))}
      </div>
      <details className="mt-3"><summary className="cursor-pointer font-semibold">Immutable revision history</summary><ol className="mt-2 space-y-2">{po.revisions.map((revision) => <li key={revision.id} className="rounded bg-surface-muted p-2 text-sm"><strong>V{revision.revision_number}</strong>{revision.predecessor_revision ? ` from V${revision.predecessor_revision}` : " original issued order"} · effective {new Date(revision.effective_at).toLocaleString()}<div>{safeSnapshotSummary(revision.effective_snapshot)}</div></li>)}</ol></details>
    </section>
  );
}
