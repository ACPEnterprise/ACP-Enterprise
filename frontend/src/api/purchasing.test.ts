import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "./client";
import {
  addPurchaseOrderLine,
  createOperationalVendor,
  transitionPurchaseOrder,
} from "./purchasing";
vi.mock("./client", () => ({ apiClient: { get: vi.fn(), post: vi.fn() } }));
describe("Purchasing API", () => {
  beforeEach(() => vi.clearAllMocks());
  it("preserves idempotent Vendor, line, and lifecycle commands", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { id: "result-1" } });
    await createOperationalVendor({
      code: "SUPPLY",
      display_name: "Supply",
      idempotency_key: "vendor-1",
    });
    expect(apiClient.post).toHaveBeenLastCalledWith(
      "/api/v1/purchasing/vendors",
      expect.objectContaining({ idempotency_key: "vendor-1" }),
    );
    await addPurchaseOrderLine("po-1", {
      expected_po_version: 2,
      description: "Fitting",
      quantity: "2",
      unit: "each",
      unit_cost: "4.25",
      idempotency_key: "line-1",
    });
    expect(apiClient.post).toHaveBeenLastCalledWith(
      "/api/v1/purchasing/purchase-orders/po-1/lines",
      expect.objectContaining({ expected_po_version: 2 }),
    );
    await transitionPurchaseOrder("po-1", "issue", {
      expected_version: 4,
      idempotency_key: "issue-1",
    });
    expect(apiClient.post).toHaveBeenLastCalledWith(
      "/api/v1/purchasing/purchase-orders/po-1/issue",
      expect.objectContaining({ expected_version: 4 }),
    );
  });
});
