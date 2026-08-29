import { useState, type FormEvent } from "react";
import type {
  PurchaseOrder,
  PurchaseOrderDispositionCommand,
} from "../types/purchasing";
import { Alert, Badge, Button, Input } from "../ui";

interface Props {
  po: PurchaseOrder;
  canClose: boolean;
  canCancel: boolean;
  pending: boolean;
  errorMessage: string | null;
  onDisposition: (
    action: "complete" | "cancel",
    input: PurchaseOrderDispositionCommand,
  ) => Promise<unknown>;
}

const activeReturnStates = new Set([
  "requested",
  "authorized",
  "return_ready",
  "returned",
  "received_by_vendor",
]);

export function PurchaseOrderDispositionControls({
  po,
  canClose,
  canCancel,
  pending,
  errorMessage,
  onDisposition,
}: Props) {
  const [action, setAction] = useState<"complete" | "cancel" | null>(null);
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const unresolvedDiscrepancies = po.discrepancies.filter(
    (item) => item.status === "open",
  ).length;
  const activeReturns = po.returns.filter((item) =>
    activeReturnStates.has(item.status),
  ).length;
  const pendingChanges = po.change_orders.filter(
    (item) => item.status === "requested",
  ).length;
  const received = po.lines.reduce(
    (total, line) => total + Number(line.cumulative_accepted_quantity),
    0,
  );
  const outstanding = po.lines.reduce(
    (total, line) => total + Number(line.outstanding_quantity),
    0,
  );
  const returned = po.returns
    .filter((item) => item.status !== "canceled")
    .reduce((total, item) => total + Number(item.quantity), 0);
  const blockers = [
    unresolvedDiscrepancies
      ? `${unresolvedDiscrepancies} unresolved discrepancy`
      : null,
    activeReturns ? `${activeReturns} active return` : null,
    pendingChanges ? `${pendingChanges} pending change request` : null,
  ].filter(Boolean);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!action) return;
    await onDisposition(action, {
      expected_po_version: po.version,
      expected_effective_revision: po.effective_revision,
      reason,
      confirm_terminal_action: confirmed,
      idempotency_key: crypto.randomUUID(),
    });
    setAction(null);
    setReason("");
    setConfirmed(false);
  };

  if (po.disposition) {
    return (
      <section className="mt-4 rounded border border-stroke p-3" aria-label={`Terminal disposition for ${po.po_number}`}>
        <div className="flex flex-wrap items-center gap-2">
          <strong>Terminal Purchasing disposition</strong>
          <Badge>{po.disposition.disposition}</Badge>
        </div>
        <div className="text-sm">Reason: {po.disposition.reason}</div>
        <div className="text-sm text-content-muted">
          Bound to PO version {po.disposition.purchase_order_version}, effective revision V{po.disposition.effective_revision}, by user {po.disposition.actor_user_id} on {new Date(po.disposition.occurred_at).toLocaleString()}.
        </div>
        <div className="text-sm text-content-muted">Evidence {po.disposition.evidence_digest.slice(0, 12)}. Historical receipts, returns, discrepancies, revisions, and lines remain available.</div>
      </section>
    );
  }

  return (
    <section className="mt-4 rounded border border-stroke p-3" aria-label={`Disposition controls for ${po.po_number}`}>
      <strong>PO closure and cancellation</strong>
      <div className="mt-2 grid gap-2 text-sm sm:grid-cols-4">
        <div>Effective revision <strong>V{po.effective_revision}</strong></div>
        <div>Accepted received <strong>{received}</strong></div>
        <div>Returned/committed <strong>{returned}</strong></div>
        <div>Outstanding <strong>{outstanding}</strong></div>
      </div>
      {blockers.length > 0 ? (
        <Alert variant="warning">Disposition is blocked by authoritative Purchasing evidence: {blockers.join(", ")}.</Alert>
      ) : (
        <p className="mt-2 text-sm text-content-muted">No discrepancy, return, or pending-change blockers are currently projected. The server revalidates all quantities and concurrent state.</p>
      )}
      {errorMessage && <Alert variant="danger">{errorMessage}</Alert>}
      <div className="mt-2 flex flex-wrap gap-2">
        {canClose && po.status === "issued" && (
          <Button onClick={() => setAction("complete")}>Record fully satisfied completion</Button>
        )}
        {canCancel && ["draft", "submitted", "approved", "issued"].includes(po.status) && (
          <Button onClick={() => setAction("cancel")}>Cancel open obligation</Button>
        )}
      </div>
      {action && (
        <form className="mt-3 grid gap-3" onSubmit={(event) => void submit(event)}>
          <Alert variant="warning">
            {action === "complete"
              ? "This records Purchasing completion only. It does not settle AP or Accounting."
              : "This preserves received history and explicitly cancels only the remaining open obligation. It creates no Inventory or financial effect."}
          </Alert>
          <Input aria-label="Terminal disposition reason" required value={reason} onChange={(event) => setReason(event.target.value)} />
          <label className="flex min-h-11 items-center gap-2">
            <input aria-label="Confirm terminal disposition" type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
            I confirm this consequential terminal disposition against the current authoritative PO state.
          </label>
          <div className="flex gap-2">
            <Button type="submit" disabled={!confirmed} loading={pending}>{action === "complete" ? "Confirm fully satisfied completion" : "Confirm cancellation"}</Button>
            <Button type="button" onClick={() => setAction(null)}>Keep PO open</Button>
          </div>
        </form>
      )}
    </section>
  );
}
