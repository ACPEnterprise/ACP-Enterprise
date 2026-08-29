import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ReplenishmentWorkbench as Result } from "../../types/purchasing";
import { ReplenishmentWorkbench } from "./ReplenishmentWorkbench";

const result: Result = {
  schema_version: 1,
  company_id: "company-1",
  as_of: "2026-08-29T12:00:00Z",
  evidence_digest: "report-digest",
  recommendations: [{ branch_id: "branch-1", inventory_item_id: "item-1", item_code: "FILTER", item_name: "Filter", stocking_unit: "each", target_available_quantity: "10", on_hand_quantity: "2", reserved_quantity: "0", available_quantity: "2", open_purchase_order_quantity: "3", recommended_order_quantity: "5", recommendation_state: "recommend_order", provenance: ["inventory:item-1"], evidence_digest: "recommendation-digest" }],
};

const baseProps = {
  pending: false, decisionPending: false, result, error: false,
  decisionError: null, decisionSucceeded: false,
  onRun: vi.fn(), onDecision: vi.fn().mockResolvedValue(undefined),
};

describe("ReplenishmentWorkbench disposition authority", () => {
  it("keeps evidence visible but hides mutation controls from read-only users", () => {
    render(<ReplenishmentWorkbench {...baseProps} canApprove={false} />);
    expect(screen.getByText("Recommended 5 each")).toBeVisible();
    expect(screen.getByText(/Recommendation evidence is read-only/)).toBeVisible();
    expect(screen.queryByRole("button", { name: /Approve and create draft PO/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Replenishment Vendor ID")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Approved quantity")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Approved unit cost")).not.toBeInTheDocument();
  });

  it("shows authorized controls and prevents duplicate actions while pending", () => {
    const { rerender } = render(<ReplenishmentWorkbench {...baseProps} canApprove />);
    expect(screen.getByLabelText("Replenishment Vendor ID")).toBeVisible();
    expect(screen.getByRole("button", { name: "Reject" })).toBeVisible();
    rerender(<ReplenishmentWorkbench {...baseProps} canApprove decisionPending />);
    expect(screen.getByLabelText("Replenishment Vendor ID")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reject" })).toBeDisabled();
  });

  it("surfaces safe decision errors without implying success", () => {
    render(<ReplenishmentWorkbench {...baseProps} canApprove decisionError="This recommendation is stale. Its evidence must be recalculated before disposition." result={undefined} />);
    expect(screen.getByText(/recommendation is stale/)).toBeVisible();
    expect(screen.queryByRole("button", { name: /Approve and create draft PO/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/recorded and reconciled/)).not.toBeInTheDocument();
  });

  it("submits one authorized disposition from one operator action", () => {
    const onDecision = vi.fn().mockResolvedValue(undefined);
    render(<ReplenishmentWorkbench {...baseProps} canApprove onDecision={onDecision} />);
    fireEvent.change(screen.getByLabelText("Replenishment Vendor ID"), { target: { value: "vendor-1" } });
    fireEvent.change(screen.getByLabelText("Replenishment PO number"), { target: { value: "PO-1" } });
    fireEvent.change(screen.getByLabelText("Approved quantity"), { target: { value: "5" } });
    fireEvent.change(screen.getByLabelText("Approved unit cost"), { target: { value: "2.50" } });
    fireEvent.change(screen.getByLabelText("Decision reason"), { target: { value: "Approved current evidence" } });
    fireEvent.click(screen.getByRole("button", { name: /Approve and create draft PO/ }));
    expect(onDecision).toHaveBeenCalledOnce();
  });
});
