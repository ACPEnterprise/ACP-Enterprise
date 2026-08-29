import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { BranchPurchasingPolicyWorkbench } from "./BranchPurchasingPolicyWorkbench";

const policy = {
  id: "policy-1",
  company_id: "company-1",
  branch_id: "branch-1",
  inventory_item_id: "item-1",
  target_available_quantity: "8.000000",
  status: "active" as const,
  provenance_reference: "approved target evidence",
  version: 2,
  revisions: [],
};

describe("BranchPurchasingPolicyWorkbench", () => {
  it("keeps read-only evidence visible without configuration controls", () => {
    render(
      <BranchPurchasingPolicyWorkbench
        policies={[policy]}
        canManage={false}
        pending={false}
        error={false}
        onSave={vi.fn()}
      />,
    );
    expect(screen.getByText(/Target 8.000000/)).toBeVisible();
    expect(screen.getByText(/Read-only policy evidence/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Save branch policy" })).not.toBeInTheDocument();
  });

  it("submits explicit scoped policy evidence for authorized managers", () => {
    const save = vi.fn().mockResolvedValue(undefined);
    render(
      <BranchPurchasingPolicyWorkbench
        policies={[]}
        canManage
        pending={false}
        error={false}
        onSave={save}
      />,
    );
    fireEvent.change(screen.getByLabelText("Policy branch ID"), { target: { value: "branch-1" } });
    fireEvent.change(screen.getByLabelText("Policy inventory item ID"), { target: { value: "item-1" } });
    fireEvent.change(screen.getByLabelText("Policy target quantity"), { target: { value: "12" } });
    fireEvent.change(screen.getByLabelText("Policy provenance"), { target: { value: "owner-reviewed-target" } });
    fireEvent.change(screen.getByLabelText("Policy reason"), { target: { value: "seasonal stocking review" } });
    fireEvent.click(screen.getByRole("button", { name: "Save branch policy" }));
    expect(save).toHaveBeenCalledWith(expect.objectContaining({
      branch_id: "branch-1",
      inventory_item_id: "item-1",
      target_available_quantity: "12",
      provenance_reference: "owner-reviewed-target",
      reason: "seasonal stocking review",
    }));
  });

  it("surfaces fail-closed save errors", () => {
    render(
      <BranchPurchasingPolicyWorkbench
        policies={[]}
        canManage
        pending={false}
        error
        onSave={vi.fn()}
      />,
    );
    expect(screen.getByText(/No target change was assumed effective/)).toBeVisible();
  });
});
