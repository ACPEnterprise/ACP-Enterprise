import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import { getAccountingPeriods } from "./accountingClose";

vi.mock("./client", () => ({ apiClient: { get: vi.fn() } }));

describe("accounting close API", () => {
  beforeEach(() => vi.clearAllMocks());

  it("reads Company-scoped Accounting periods without constructing close evidence", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: [] });
    await getAccountingPeriods();
    expect(apiClient.get).toHaveBeenCalledWith("/api/v1/accounting/periods");
  });
});
