import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { PurchaseOrder } from "../types/purchasing";
import { PurchaseOrderChangeControls } from "./PurchaseOrderChangeControls";

const po: PurchaseOrder = {
  id: "po-1", branch_id: "branch-1", vendor_id: "vendor-1", po_number: "PO-1",
  status: "issued", currency: "USD", expected_date: null, version: 8,
  effective_revision: 2, issuance_digest: "digest", receiving_status: "partially_received",
  lines: [{ id: "line-1", line_number: 1, inventory_item_id: null, description: "Valve", quantity: "10", unit: "each", unit_cost: "4.00", extended_cost: "40", version: 1, cumulative_accepted_quantity: "3", outstanding_quantity: "7", is_cancelled: false }],
  receipts: [], discrepancies: [], returns: [],
  change_orders: [{ id: "change-1", change_identity: "CO-1", base_revision: 2, proposed_changes: [{ operation: "set_quantity", line_id: "line-1", quantity: "12" }], reason: "Vendor confirmed quantity", status: "requested", requested_by_user_id: "user-1", requested_at: "2026-08-28T12:00:00Z", decided_by_user_id: null, decided_at: null, effective_revision: null, evidence_digest: "evidence", downstream_reconciliation_required: false }],
  revisions: [{ id: "revision-1", revision_number: 1, predecessor_revision: null, change_order_id: null, effective_snapshot: { lines: [{ quantity: "10" }], expected_date: null }, evidence_digest: "original", effective_by_user_id: "user-1", effective_at: "2026-08-27T12:00:00Z" }],
};

describe("PurchaseOrderChangeControls", () => {
  it("separates authoritative and proposed values and submits a reason", async () => {
    const request = vi.fn().mockResolvedValue(undefined);
    render(<PurchaseOrderChangeControls po={po} canRequest canApprove={false} requestPending={false} decisionPending={false} errorMessage={null} onRequest={request} onDecision={vi.fn()} />);
    expect(screen.getByText(/current effective revision V2/i)).toBeVisible();
    expect(screen.getAllByText("requested", { exact: false })[0]).toBeVisible();
    expect(screen.queryByRole("button", { name: "Approve change" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Request PO change" }));
    await userEvent.type(screen.getByLabelText("Proposed value"), "15");
    await userEvent.type(screen.getByLabelText("Change reason"), "Revised vendor quantity");
    expect(screen.getByText(/Current authoritative value:/).parentElement).toHaveTextContent("10");
    expect(screen.getByText(/Proposed value:/).parentElement).toHaveTextContent("15");
    await userEvent.click(screen.getByRole("button", { name: "Submit change request" }));
    expect(request).toHaveBeenCalledWith(expect.objectContaining({ expected_po_version: 8, base_revision: 2, reason: "Revised vendor quantity" }));
  });

  it("shows approval only to approvers and surfaces stale refresh guidance", () => {
    const { rerender } = render(<PurchaseOrderChangeControls po={po} canRequest={false} canApprove requestPending={false} decisionPending={false} errorMessage={null} onRequest={vi.fn()} onDecision={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Approve change" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Request PO change" })).not.toBeInTheDocument();
    rerender(<PurchaseOrderChangeControls po={po} canRequest={false} canApprove requestPending={false} decisionPending={false} errorMessage="This PO changed while you were reviewing it. Authoritative state was refreshed; review the current revision before trying again." onRequest={vi.fn()} onDecision={vi.fn()} />);
    expect(screen.getByText(/Authoritative state was refreshed/)).toBeVisible();
  });
});
