import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProcurementMatchWorkbench } from "./ProcurementMatchWorkbench";

const mutateAsync = vi.fn();
const hookState = {
  query: { data: undefined, error: null },
  evaluate: { data: undefined, error: null, isPending: false, mutateAsync },
  resolve: { data: undefined, error: null, isPending: false, mutateAsync },
};

vi.mock("../../hooks/useProcurementMatching", () => ({
  useProcurementMatch: () => hookState.query,
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
    expect(screen.queryByRole("button", { name: "Evaluate match" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Purchase Order identity")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Vendor Bill identity")).not.toBeInTheDocument();
  });

  it("shows governed evaluation inputs only with match-review authority", () => {
    render(<ProcurementMatchWorkbench canReview />);
    expect(screen.getByLabelText("Purchase Order identity")).toBeVisible();
    expect(screen.getByLabelText("Vendor Bill identity")).toBeVisible();
    expect(screen.getByRole("button", { name: "Evaluate match" })).toBeVisible();
  });
});
