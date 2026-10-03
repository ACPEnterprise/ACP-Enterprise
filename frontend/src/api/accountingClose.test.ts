import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import {
  closeAccountingPeriod,
  getAccountantReview,
  getAccountingPeriods,
  getPeriodCloseReadiness,
  getReportComparisons,
} from "./accountingClose";

vi.mock("./client", () => ({ apiClient: { get: vi.fn(), post: vi.fn() } }));

describe("accounting close API", () => {
  beforeEach(() => vi.clearAllMocks());

  it("reads Company-scoped Accounting periods without constructing close evidence", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: [] });
    await getAccountingPeriods();
    expect(apiClient.get).toHaveBeenCalledWith("/api/v1/accounting/periods");
  });

  it("reads canonical comparisons, accountant review, and readiness routes", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: [] });
    await getReportComparisons("period-1");
    await getAccountantReview();
    await getPeriodCloseReadiness("period-1");
    expect(apiClient.get).toHaveBeenNthCalledWith(
      1,
      "/api/v1/accounting/periods/period-1/report-comparisons",
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(
      2,
      "/api/v1/accounting/accountant-review",
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(
      3,
      "/api/v1/accounting/periods/period-1/close-readiness",
    );
  });

  it("submits only version, reason, and the current server readiness digest", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { id: "period-1" } });
    await closeAccountingPeriod({
      periodId: "period-1",
      expectedVersion: 4,
      reason: "September close reviewed",
      readinessDigest: "d".repeat(64),
    });
    expect(apiClient.post).toHaveBeenCalledWith(
      "/api/v1/accounting/periods/period-1/close",
      {
        expected_version: 4,
        reason: "September close reviewed",
        readiness_digest: "d".repeat(64),
      },
    );
    const body = vi.mocked(apiClient.post).mock.calls[0]?.[1];
    expect(body).not.toHaveProperty("controls_reconciled");
    expect(body).not.toHaveProperty("evidence_digest");
    expect(body).not.toHaveProperty("finance_approver_user_id");
  });
});
