import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import { confirmBankImport, getCashFlow, getMatchReview, previewBankImport } from "./banking";

vi.mock("./client", () => ({ apiClient: { get: vi.fn(), post: vi.fn() } }));

const request = {
  statement_identity: "statement-2026-09",
  period_start: "2026-09-01",
  period_end: "2026-09-30",
  opening_balance: "1000.00",
  ending_balance: "1250.00",
  transactions: [],
};

describe("banking API", () => {
  beforeEach(() => vi.clearAllMocks());

  it("keeps preview non-mutating and submits the exact preview digest on confirmation", async () => {
    vi.mocked(apiClient.post)
      .mockResolvedValueOnce({ data: { preview_digest: "preview-digest" } })
      .mockResolvedValueOnce({ data: { persisted_count: 0 } });

    await previewBankImport("bank-1", request);
    await confirmBankImport("bank-1", request, "preview-digest");

    expect(apiClient.post).toHaveBeenNthCalledWith(
      1,
      "/api/v1/accounting/banking/accounts/bank-1/imports/preview",
      request,
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      2,
      "/api/v1/accounting/banking/accounts/bank-1/imports/confirm",
      { ...request, preview_digest: "preview-digest" },
    );
  });

  it("uses account-scoped review and posted cash-movement parameters", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: [] });

    await getMatchReview("bank-1");
    await getCashFlow("2026-09-01", "2026-09-30");

    expect(apiClient.get).toHaveBeenNthCalledWith(
      1,
      "/api/v1/accounting/banking/match-review",
      { params: { bank_account_id: "bank-1" } },
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(
      2,
      "/api/v1/accounting/banking/cash-flow",
      {
        params: {
          period_start: "2026-09-01",
          period_end: "2026-09-30",
          basis: "posted_cash_movement",
        },
      },
    );
  });
});
