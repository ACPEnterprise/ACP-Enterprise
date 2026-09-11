import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "./client";
import { getQboAccountingEvidence } from "./qboAccountingEvidence";

vi.mock("./client", () => ({ apiClient: { get: vi.fn() } }));

describe("QBO accounting source evidence API", () => {
  beforeEach(() => vi.clearAllMocks());

  it("requests read-only evidence with an explicit accounting basis", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: { source: "quickbooks_online" },
    });
    await getQboAccountingEvidence("cash");
    expect(apiClient.get).toHaveBeenCalledWith(
      "/api/v1/accounting/source-evidence/qbo",
      { params: { basis: "cash" } },
    );
  });
});
