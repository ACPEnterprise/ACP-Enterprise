import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProcurementMatchWorkbench } from "./ProcurementMatchWorkbench";

const mutateAsync = vi.fn();
const hookState = {
  query: { data: undefined, error: null },
  evaluate: { data: undefined, error: null, isPending: false, mutateAsync },
  resolve: { data: undefined, error: null, isPending: false, mutateAsync },
  candidates: {
    data: [
      {
        vendor_bill_id: "bill-1",
        vendor_bill_number: "BILL-1",
        vendor_bill_version: 2,
        purchase_order_id: "po-1",
        purchase_order_number: "PO-1",
        purchase_order_version: 3,
        linkage_state: "ready",
        active_match_id: null,
      },
    ],
    isError: false,
  },
};

vi.mock("../../hooks/useProcurementMatching", () => ({
  useProcurementMatch: () => hookState.query,
  useProcurementMatchCandidates: () => hookState.candidates,
  useProcurementMatchMutations: () => ({
    evaluate: hookState.evaluate,
    resolve: hookState.resolve,
  }),
}));

describe("ProcurementMatchWorkbench authority", () => {
  beforeEach(() => {
    mutateAsync.mockReset();
    hookState.query.data = undefined;
    hookState.query.error = null;
    hookState.evaluate.error = null;
    hookState.resolve.error = null;
  });

  it("preserves lookup visibility but hides every matching mutation from read-only users", () => {
    render(<ProcurementMatchWorkbench canReview={false} />);
    expect(screen.getByLabelText("Match identity")).toBeVisible();
    expect(screen.getByText(/Read-only access/)).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Evaluate match" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByLabelText("Purchase Order identity"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByLabelText("Vendor Bill identity"),
    ).not.toBeInTheDocument();
  });

  it("shows governed evaluation inputs only with match-review authority", () => {
    render(<ProcurementMatchWorkbench canReview />);
    fireEvent.change(screen.getByLabelText("PO-backed Vendor Bill candidate"), {
      target: { value: "bill-1" },
    });
    expect(screen.getByLabelText("Purchase Order identity")).toBeVisible();
    expect(screen.getByLabelText("Vendor Bill identity")).toBeVisible();
    expect(screen.getByLabelText("Purchase Order identity")).toHaveValue(
      "po-1",
    );
    expect(screen.getByLabelText("Vendor Bill identity")).toHaveValue("bill-1");
    expect(
      screen.getByRole("button", { name: "Evaluate match" }),
    ).toBeVisible();
  });
});
