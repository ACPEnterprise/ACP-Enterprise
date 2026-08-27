import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import { getFinancialReport } from "./financialReporting";

vi.mock("./client", () => ({ apiClient: { get: vi.fn() } }));

describe("financial reporting API", () => {
  beforeEach(() => vi.clearAllMocks());

  it("requests an as-of trial balance from the native ledger", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: {} });
    await getFinancialReport({
      report: "trial-balance",
      startDate: "2026-01-01",
      endDate: "2026-08-27",
    });
    expect(apiClient.get).toHaveBeenCalledWith(
      "/api/v1/accounting/reports/trial-balance",
      { params: { as_of: "2026-08-27" } },
    );
  });

  it("preserves explicit range and Branch scope for GL detail", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: {} });
    await getFinancialReport({
      report: "general-ledger",
      startDate: "2026-01-01",
      endDate: "2026-08-27",
      branchId: "branch-1",
    });
    expect(apiClient.get).toHaveBeenCalledWith(
      "/api/v1/accounting/reports/general-ledger",
      {
        params: {
          start_date: "2026-01-01",
          end_date: "2026-08-27",
          branch_id: "branch-1",
        },
      },
    );
  });
});
