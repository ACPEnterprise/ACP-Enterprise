import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PriceBookReviewQueue } from "./PriceBookReviewQueue";

const state = vi.hoisted(() => ({ bulk: vi.fn(), decision: vi.fn() }));
vi.mock("../../hooks/usePriceBook", () => ({
  usePriceBookReview: () => ({
    data: {
      rows: [{
        service_item_id: "item-1", price_version_id: "version-1", item_version: 1, price_version: 1,
        code: "SVC-001", name: "Diagnostic visit", customer_description: "Diagnostic visit",
        category_name: "Service Calls", branch_name: "Main", proposed_price: "129.00", currency: "USD",
        effective_at: "2026-09-15T13:00:00Z", tax_classification_name: null, labor_quantity: "1", material_quantity: null,
        labor_cost: "45.00", material_cost: null, source_identity: "flat-rate:SVC-001", candidate_state: "INCOMPLETE",
        activation_readiness: "NOT_READY", missing_evidence_reasons: ["Material quantity is required; it was not assumed to be zero."],
        conflict_reasons: [], management_review_complete: false,
      }],
    },
    isLoading: false,
    isError: false,
  }),
  usePriceBookMutations: () => ({
    bulkReview: { mutateAsync: state.bulk, isPending: false, isError: false },
    reviewDecision: { mutateAsync: state.decision, isPending: false, isError: false },
  }),
}));

describe("PriceBookReviewQueue", () => {
  beforeEach(() => { state.bulk.mockReset().mockResolvedValue({ rows: [] }); state.decision.mockReset().mockResolvedValue({}); });

  it("shows evidence gaps and permits only non-activation bulk edits", async () => {
    render(<PriceBookReviewQueue categories={[{ id: "category-1", company_id: "company-1", parent_id: null, code: "SERVICE", name: "Service Calls", description: null, status: "active", version: 1 }]} taxes={[{ id: "tax-1", company_id: "company-1", code: "TAX", name: "Taxable", taxable: true, status: "active", version: 1 }]} branches={[{ id: "branch-1", name: "Main" }]} />);
    expect(screen.getByText("Material quantity is required; it was not assumed to be zero.")).toBeVisible();
    expect(screen.queryByRole("button", { name: /activate/i })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/internal id/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Select SVC-001"));
    fireEvent.change(screen.getByLabelText("Bulk category"), { target: { value: "category-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply reviewed metadata" }));
    await waitFor(() => expect(state.bulk).toHaveBeenCalledWith(expect.objectContaining({ category_id: "category-1", targets: [expect.objectContaining({ price_version_id: "version-1" })] })));
  });
});
