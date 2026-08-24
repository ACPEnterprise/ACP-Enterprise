import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "./client";
import { applyPayment, collectPayment, refundPayment } from "./payments";

vi.mock("./client", () => ({ apiClient: { post: vi.fn(), get: vi.fn() } }));

describe("Payments API", () => {
  beforeEach(() => vi.clearAllMocks());
  it("preserves opaque, idempotent collection and application evidence", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { id: "payment-1" } });
    await collectPayment({ branch_id: "branch-1", customer_id: "customer-1", amount: "20.00", currency: "USD", opaque_payment_method: "opaque_test_success", idempotency_key: "collect-1" });
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/payments/intents", expect.objectContaining({ opaque_payment_method: "opaque_test_success", idempotency_key: "collect-1" }));
    await applyPayment("receipt-1", { branch_id: "branch-1", invoice_id: "invoice-1", amount: "10.00", expected_invoice_version: 2, idempotency_key: "apply-1", occurred_at: "2026-08-21T12:00:00Z" });
    expect(apiClient.post).toHaveBeenLastCalledWith("/api/v1/payments/receipts/receipt-1/applications", expect.objectContaining({ invoice_id: "invoice-1", amount: "10.00" }));
    await refundPayment("receipt-1", { branch_id: "branch-1", amount: "5.00", reason: "customer request", expected_version: 3, idempotency_key: "refund-1" });
    expect(apiClient.post).toHaveBeenLastCalledWith("/api/v1/payments/receipts/receipt-1/refunds", expect.objectContaining({ expected_version: 3 }));
  });
});
