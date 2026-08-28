import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "./client";
import {
  addPurchaseOrderLine,
  createOperationalVendor,
  recordPurchaseOrderReceipt,
  resolvePurchaseOrderDiscrepancy,
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
    await recordPurchaseOrderReceipt("po-1", {
      expected_po_version: 5,
      receiving_event_identity: "dock-1",
      received_at: "2026-08-28T19:00:00Z",
      effective_date: "2026-08-28",
      idempotency_key: "receipt-1",
      lines: [
        {
          purchase_order_line_id: "line-1",
          accepted_quantity: "2",
          rejected_quantity: "0",
        },
      ],
    });
    expect(apiClient.post).toHaveBeenLastCalledWith(
      "/api/v1/purchasing/purchase-orders/po-1/receipts",
      expect.objectContaining({ idempotency_key: "receipt-1" }),
    );
    await resolvePurchaseOrderDiscrepancy("po-1", "disc-1", {
      expected_po_version: 6,
      expected_discrepancy_version: 1,
      resolution: "resolved_rejected",
      note: "Return damaged item",
      idempotency_key: "resolve-1",
    });
    expect(apiClient.post).toHaveBeenLastCalledWith(
      "/api/v1/purchasing/purchase-orders/po-1/discrepancies/disc-1/resolve",
      expect.objectContaining({ resolution: "resolved_rejected" }),
    );
  });
});
