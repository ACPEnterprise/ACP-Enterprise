import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BulkDraftWorkspace } from "./BulkDraftWorkspace";

const state = vi.hoisted(() => ({ validate: vi.fn(), create: vi.fn() }));
vi.mock("../../hooks/usePriceBook", () => ({
  usePriceBookMutations: () => ({
    validateBulk: { mutateAsync: state.validate, isPending: false, isError: false },
    createBulk: { mutateAsync: state.create, isPending: false, isError: false },
  }),
}));

describe("BulkDraftWorkspace", () => {
  beforeEach(() => { state.validate.mockReset(); state.create.mockReset(); });

  it("imports rows, reports incompleteness, and never offers activation", async () => {
    state.validate.mockImplementation(async (rows: Array<{ client_ref: string }>) => ({ can_save: true, rows: [{ client_ref: rows[0].client_ref, can_save: true, readiness: "INCOMPLETE", issues: [{ code: "MISSING_COST_AUTHORITY", field: "components", message: "Internal cost remains unavailable." }] }] }));
    render(<BulkDraftWorkspace branchId="branch-1" categories={[{ id: "category-1", company_id: "company-1", parent_id: null, code: "DRAIN", name: "Drain", description: null, status: "active", version: 1 }]} taxes={[{ id: "tax-1", company_id: "company-1", code: "TAX", name: "Taxable", taxable: true, status: "active", version: 1 }]} />);
    fireEvent.change(screen.getByLabelText("Paste draft services"), { target: { value: "flat-rate:DRAIN-1\tDRAIN-1\tDrain clearing\tClear one drain\t125\t1.5\t1" } });
    fireEvent.click(screen.getByRole("button", { name: "Load pasted rows" }));
    fireEvent.change(screen.getByLabelText("Service category 1"), { target: { value: "category-1" } });
    fireEvent.change(screen.getByLabelText("Tax classification 1"), { target: { value: "tax-1" } });
    fireEvent.change(screen.getByLabelText("Effective date 1"), { target: { value: "2026-09-15T09:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Validate drafts" }));
    await waitFor(() => expect(state.validate).toHaveBeenCalled());
    expect(await screen.findByText("Incomplete")).toBeVisible();
    expect(screen.getByText("Internal cost remains unavailable.")).toBeVisible();
    expect(screen.queryByRole("button", { name: /activate/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save validated drafts" })).toBeEnabled();
  });
});
