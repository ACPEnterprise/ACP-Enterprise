import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  useBranchPurchasingPolicies,
  usePurchasing,
  usePurchasingMutations,
} from "../hooks/usePurchasing";
import { PurchasingRoute } from "./PurchasingRoute";
let permissions = new Set<string>();
vi.mock("../auth", () => ({
  useAuth: () => ({
    activeCompany: { branches: [{ id: "branch-1", name: "Main" }] },
  }),
  useHasPermission: (code: string) => permissions.has(code),
}));
vi.mock("../hooks/usePurchasing", () => ({
  usePurchasing: vi.fn(),
  useBranchPurchasingPolicies: vi.fn(),
  usePurchasingMutations: vi.fn(),
}));
vi.mock("../hooks/useInventory", () => ({
  useInventory: () => ({
    isPending: false,
    isError: false,
    data: { locations: [] },
  }),
}));
vi.mock("../hooks/useProcurementMatching", () => ({
  useVendorPerformance: () => ({
    isPending: false,
    isError: false,
    data: { items: [] },
  }),
  useProcurementMatch: () => ({ data: undefined, error: null }),
  useProcurementMatchCandidates: () => ({ data: [], isError: false }),
  useProcurementMatchMutations: () => ({
    evaluate: { ...mutation, data: undefined, error: null },
    resolve: { ...mutation, data: undefined, error: null },
  }),
}));
const mutation = { mutateAsync: vi.fn(), isPending: false, isError: false };
const replenishmentMutation = {
  ...mutation,
  data: undefined as never,
  reset: vi.fn(),
};
const decisionMutation = {
  ...mutation,
  error: null as unknown,
  isSuccess: false,
  reset: vi.fn(),
};
describe("PurchasingRoute", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    replenishmentMutation.data = undefined as never;
    decisionMutation.error = null;
    decisionMutation.isSuccess = false;
    permissions = new Set(["COMPANY_PURCHASING_READ"]);
    vi.mocked(usePurchasing).mockReturnValue({
      isPending: false,
      isError: false,
      data: {
        vendors: [
          {
            id: "vendor-1",
            code: "SUPPLY",
            display_name: "Supply House",
            status: "active",
          },
        ],
        purchase_orders: [
          {
            id: "po-1",
            po_number: "PO-1",
            branch_id: "branch-1",
            vendor_id: "vendor-1",
            status: "submitted",
            currency: "USD",
            version: 3,
            effective_revision: 1,
            lines: [],
            issuance_digest: null,
            receiving_status: "not_received",
            receipts: [],
            discrepancies: [],
            returns: [],
            change_orders: [],
            revisions: [],
            disposition: null,
          },
        ],
      },
    } as never);
    vi.mocked(useBranchPurchasingPolicies).mockReturnValue({
      isError: false,
      data: [],
    } as never);
    vi.mocked(usePurchasingMutations).mockReturnValue({
      createVendor: mutation,
      updateVendor: mutation,
      createOrder: mutation,
      updateOrder: mutation,
      addLine: mutation,
      updateLine: mutation,
      transition: mutation,
      recordReceipt: mutation,
      resolveDiscrepancy: mutation,
      createReturn: mutation,
      transitionReturn: mutation,
      requestChange: mutation,
      decideChange: mutation,
      dispositionOrder: mutation,
      replenishmentWorkbench: replenishmentMutation,
      decideReplenishment: decisionMutation,
      configureBranchPolicy: mutation,
      createRequisition: mutation,
      transitionRequisition: mutation,
      configureSupplyChainPolicy: mutation,
    } as never);
  });
  it("keeps recommendations read-only without approval authority", () => {
    replenishmentMutation.data = {
      schema_version: 1,
      company_id: "company-1",
      as_of: "2026-08-29T12:00:00Z",
      evidence_digest: "report",
      recommendations: [
        {
          branch_id: "branch-1",
          inventory_item_id: "item-1",
          item_code: "FILTER",
          item_name: "Filter",
          stocking_unit: "each",
          target_available_quantity: "10",
          on_hand_quantity: "2",
          reserved_quantity: "0",
          available_quantity: "2",
          open_purchase_order_quantity: "3",
          recommended_order_quantity: "5",
          recommendation_state: "recommend_order",
          provenance: [],
          evidence_digest: "recommendation",
        },
      ],
    } as never;
    render(<PurchasingRoute />);
    expect(screen.getByText("Recommended 5 each")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /Approve and create draft PO/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Reject" }),
    ).not.toBeInTheDocument();
  });
  it("surfaces stale decision failure and removes the stale actionable result", async () => {
    permissions.add("COMPANY_PURCHASING_APPROVE");
    replenishmentMutation.data = {
      schema_version: 1,
      company_id: "company-1",
      as_of: "2026-08-29T12:00:00Z",
      evidence_digest: "report",
      recommendations: [
        {
          branch_id: "branch-1",
          inventory_item_id: "item-1",
          item_code: "FILTER",
          item_name: "Filter",
          stocking_unit: "each",
          target_available_quantity: "10",
          on_hand_quantity: "2",
          reserved_quantity: "0",
          available_quantity: "2",
          open_purchase_order_quantity: "3",
          recommended_order_quantity: "5",
          recommendation_state: "recommend_order",
          provenance: [],
          evidence_digest: "recommendation",
        },
      ],
    } as never;
    const staleError = {
      isAxiosError: true,
      response: {
        status: 409,
        data: { detail: "STALE_REPLENISHMENT_RECOMMENDATION" },
      },
    };
    decisionMutation.mutateAsync.mockRejectedValueOnce(staleError);
    decisionMutation.error = staleError;
    render(<PurchasingRoute />);
    fireEvent.change(screen.getByLabelText("Replenishment Vendor ID"), {
      target: { value: "vendor-1" },
    });
    fireEvent.change(screen.getByLabelText("Replenishment PO number"), {
      target: { value: "PO-1" },
    });
    fireEvent.change(screen.getByLabelText("Approved quantity"), {
      target: { value: "5" },
    });
    fireEvent.change(screen.getByLabelText("Approved unit cost"), {
      target: { value: "2" },
    });
    fireEvent.change(screen.getByLabelText("Decision reason"), {
      target: { value: "Current evidence" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /Approve and create draft PO/ }),
    );
    await waitFor(() =>
      expect(replenishmentMutation.reset).toHaveBeenCalledOnce(),
    );
    expect(screen.getByText(/recommendation is stale/)).toBeVisible();
  });
  it("fails closed without read permission", () => {
    permissions.clear();
    render(<PurchasingRoute />);
    expect(
      screen.getByText("You are not authorized to view Purchasing."),
    ).toBeVisible();
  });
  it("separates read, manage, approve, and issue controls", () => {
    render(<PurchasingRoute />);
    expect(screen.getByText("PO-1")).toBeVisible();
    expect(
      screen.queryByText("Create operational Vendor"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Approve")).not.toBeInTheDocument();
    permissions = new Set([
      "COMPANY_PURCHASING_READ",
      "COMPANY_PURCHASING_MANAGE",
      "COMPANY_PURCHASING_APPROVE",
    ]);
    render(<PurchasingRoute />);
    expect(screen.getByText("Create operational Vendor")).toBeVisible();
    expect(screen.getByRole("button", { name: "Approve" })).toBeVisible();
    expect(screen.queryByText("Issue")).not.toBeInTheDocument();
  });
});
