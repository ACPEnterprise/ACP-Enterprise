import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import { applyQboSafeMajority, getQboApplicationLedger, getQboReviewQueue } from "./qboNativeApplication";

vi.mock("./client", () => ({ apiClient: { get: vi.fn(), post: vi.fn() } }));

describe("QBO native application API", () => {
  beforeEach(() => vi.clearAllMocks());

  it("uses the governed ledger, review queue, and explicit application command", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { items: [] } });
    vi.mocked(apiClient.post).mockResolvedValue({ data: { processed: 0 } });
    await getQboApplicationLedger();
    await getQboReviewQueue();
    await applyQboSafeMajority();
    expect(apiClient.get).toHaveBeenNthCalledWith(1, "/api/v1/accounting/source-evidence/qbo/native-application");
    expect(apiClient.get).toHaveBeenNthCalledWith(2, "/api/v1/accounting/source-evidence/qbo/native-application/review-queue");
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/accounting/source-evidence/qbo/native-application");
  });
});
