import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "./client";
import {
  getQboAccountingEvidence,
  getQboSourceBackedGeneralLedger,
} from "./qboAccountingEvidence";

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

  it("requests a bounded sealed General Ledger period", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { rows: [] } });
    await getQboSourceBackedGeneralLedger({
      startDate: "2026-05-01",
      endDate: "2026-05-31",
      basis: "accrual",
      limit: 50,
      offset: 100,
    });
    expect(apiClient.get).toHaveBeenCalledWith(
      "/api/v1/accounting/source-evidence/qbo/reports/general-ledger",
      {
        params: {
          start_date: "2026-05-01",
          end_date: "2026-05-31",
          basis: "accrual",
          limit: 50,
          offset: 100,
        },
      },
    );
  });
});
