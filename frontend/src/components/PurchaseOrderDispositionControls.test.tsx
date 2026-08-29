import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { PurchaseOrder } from "../types/purchasing";
import { PurchaseOrderDispositionControls } from "./PurchaseOrderDispositionControls";

const po: PurchaseOrder = {
  id: "po-1", branch_id: "branch-1", vendor_id: "vendor-1", po_number: "PO-1",
  status: "issued", currency: "USD", expected_date: null, version: 8,
  effective_revision: 2, issuance_digest: "digest", receiving_status: "partially_received",
  lines: [{ id: "line-1", line_number: 1, inventory_item_id: null, description: "Valve", quantity: "10", unit: "each", unit_cost: "4", extended_cost: "40", version: 1, cumulative_accepted_quantity: "4", outstanding_quantity: "6", is_cancelled: false }],
  receipts: [], discrepancies: [], returns: [], change_orders: [], revisions: [], disposition: null,
};

describe("PurchaseOrderDispositionControls", () => {
  it("requires explicit confirmation and submits current version evidence", async () => {
    const submit = vi.fn().mockResolvedValue(undefined);
    render(<PurchaseOrderDispositionControls po={po} canClose canCancel pending={false} errorMessage={null} onDisposition={submit} />);
    expect(screen.getByText(/Accepted received/).parentElement).toHaveTextContent("4");
    expect(screen.getByText(/Outstanding/).parentElement).toHaveTextContent("6");
    await userEvent.click(screen.getByRole("button", { name: "Cancel open obligation" }));
    const confirm = screen.getByRole("button", { name: "Confirm cancellation" });
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Terminal disposition reason"), "Vendor cannot fulfill remainder");
    await userEvent.click(screen.getByLabelText("Confirm terminal disposition"));
    await userEvent.click(confirm);
    expect(submit).toHaveBeenCalledWith("cancel", expect.objectContaining({ expected_po_version: 8, expected_effective_revision: 2, confirm_terminal_action: true }));
  });

  it("hides mutation controls from readers and preserves terminal evidence", () => {
    const terminal = { ...po, status: "cancelled", disposition: { id: "d-1", purchase_order_version: 8, effective_revision: 2, prior_status: "issued", disposition: "remainder_canceled" as const, reason: "Vendor cannot fulfill remainder", quantity_evidence: [], evidence_digest: "1234567890abcdef", actor_user_id: "user-1", occurred_at: "2026-08-28T12:00:00Z" } };
    const { rerender } = render(<PurchaseOrderDispositionControls po={po} canClose={false} canCancel={false} pending={false} errorMessage={null} onDisposition={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /Record fully satisfied/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Cancel open obligation/ })).not.toBeInTheDocument();
    rerender(<PurchaseOrderDispositionControls po={terminal} canClose canCancel pending={false} errorMessage={null} onDisposition={vi.fn()} />);
    expect(screen.getByText("remainder_canceled")).toBeVisible();
    expect(screen.getByText(/Vendor cannot fulfill remainder/)).toBeVisible();
  });
});
