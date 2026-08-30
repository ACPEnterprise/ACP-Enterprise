import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "./client";
import { creditInvoice, createInvoice, issueInvoice, voidInvoice, writeOffInvoice } from "./invoices";

vi.mock("./client", () => ({ apiClient: { post: vi.fn(), get: vi.fn() } }));

describe("Invoice API", () => {
  beforeEach(() => vi.clearAllMocks());
  it("preserves accepted-work and idempotency evidence", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { id: "invoice-1" } });
    await createInvoice({
      branch_id: "branch-1",
      estimate_id: "estimate-1",
      job_id: "job-1",
      due_date: "2026-08-21",
      terms: "Net 30",
      idempotency_key: "create-1",
    });
    expect(apiClient.post).toHaveBeenCalledWith(
      "/api/v1/invoices",
      expect.objectContaining({
        estimate_id: "estimate-1",
        job_id: "job-1",
        idempotency_key: "create-1",
      }),
    );
    await issueInvoice("invoice-1", {
      branch_id: "branch-1",
      expected_version: 1,
      idempotency_key: "issue-1",
      occurred_at: "2026-08-13T12:00:00Z",
    });
    expect(apiClient.post).toHaveBeenLastCalledWith(
      "/api/v1/invoices/invoice-1/issue",
      expect.objectContaining({ expected_version: 1 }),
    );
  });
  it("uses explicit append-only adjustment endpoints", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { id: "invoice-1" } });
    const amount = { branch_id: "branch-1", expected_version: 2, idempotency_key: "adjust-1", occurred_at: "2026-08-30T12:00:00Z", amount: "10.00", reason_code: "CUSTOMER_CREDIT" };
    await creditInvoice("invoice-1", amount);
    expect(apiClient.post).toHaveBeenLastCalledWith("/api/v1/invoices/invoice-1/credits", amount);
    await writeOffInvoice("invoice-1", { ...amount, idempotency_key: "writeoff-1" });
    expect(apiClient.post).toHaveBeenLastCalledWith("/api/v1/invoices/invoice-1/write-offs", expect.objectContaining({ reason_code: "CUSTOMER_CREDIT" }));
    await voidInvoice("invoice-1", { branch_id: "branch-1", expected_version: 3, idempotency_key: "void-1", occurred_at: "2026-08-30T12:00:00Z" });
    expect(apiClient.post).toHaveBeenLastCalledWith("/api/v1/invoices/invoice-1/void", expect.objectContaining({ expected_version: 3 }));
  });
});
