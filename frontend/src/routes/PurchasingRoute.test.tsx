import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { usePurchasing, usePurchasingMutations } from "../hooks/usePurchasing";
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
  usePurchasingMutations: vi.fn(),
}));
const mutation = { mutateAsync: vi.fn(), isPending: false, isError: false };
describe("PurchasingRoute", () => {
  beforeEach(() => {
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
    } as never);
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
