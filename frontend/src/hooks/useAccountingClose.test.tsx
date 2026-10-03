import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api/accountingClose";
import { useGovernedPeriodClose } from "./useAccountingClose";

vi.mock("../api/accountingClose", async (load) => {
  const actual = await load<typeof import("../api/accountingClose")>();
  return {
    ...actual,
    getPeriodCloseReadiness: vi.fn(),
    closeAccountingPeriod: vi.fn(),
  };
});

const readiness = (state: "READY" | "BLOCKED", digest: string) => ({
  period_id: "period-1",
  start_date: "2026-09-01",
  end_date: "2026-09-30",
  lifecycle_status: "closing",
  accounting_basis: "accrual",
  currency: "USD",
  opening_equity_readiness: state,
  trial_balance_readiness: state,
  ar_readiness: state,
  ap_readiness: state,
  payroll_readiness: state,
  report_comparison_readiness: state,
  accountant_review_blocker_count: state === "READY" ? 0 : 1,
  required_approvals: ["FINANCE_APPROVE"],
  blockers: [],
  overall_readiness: state,
  evidence_digest: digest,
  generated_at: "2026-10-03T12:00:00Z",
});

describe("useGovernedPeriodClose", () => {
  let client: QueryClient;
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );

  beforeEach(() => {
    client = new QueryClient({
      defaultOptions: { mutations: { retry: false } },
    });
    vi.clearAllMocks();
  });

  it("refreshes readiness immediately and sends the newly returned digest", async () => {
    vi.mocked(api.getPeriodCloseReadiness).mockResolvedValue(
      readiness("READY", "n".repeat(64)),
    );
    vi.mocked(api.closeAccountingPeriod).mockResolvedValue({
      id: "period-1",
      company_id: "company-1",
      name: "September",
      start_date: "2026-09-01",
      end_date: "2026-09-30",
      status: "closed",
      version: 5,
    });
    const { result } = renderHook(() => useGovernedPeriodClose(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({
        periodId: "period-1",
        expectedVersion: 4,
        reason: "Reviewed close",
      });
    });
    expect(api.getPeriodCloseReadiness).toHaveBeenCalledTimes(1);
    expect(api.closeAccountingPeriod).toHaveBeenCalledWith({
      periodId: "period-1",
      expectedVersion: 4,
      reason: "Reviewed close",
      readinessDigest: "n".repeat(64),
    });
    expect(
      vi.mocked(api.getPeriodCloseReadiness).mock.invocationCallOrder[0],
    ).toBeLessThan(
      vi.mocked(api.closeAccountingPeriod).mock.invocationCallOrder[0]!,
    );
  });

  it("fails closed without a close request when refreshed readiness is blocked", async () => {
    vi.mocked(api.getPeriodCloseReadiness).mockResolvedValue(
      readiness("BLOCKED", "b".repeat(64)),
    );
    const { result } = renderHook(() => useGovernedPeriodClose(), { wrapper });
    await expect(
      act(async () =>
        result.current.mutateAsync({
          periodId: "period-1",
          expectedVersion: 4,
          reason: "Reviewed close",
        }),
      ),
    ).rejects.toThrow("PERIOD_CLOSE_BLOCKED");
    expect(api.closeAccountingPeriod).not.toHaveBeenCalled();
  });

  it("does not retry a stale-readiness rejection", async () => {
    vi.mocked(api.getPeriodCloseReadiness).mockResolvedValue(
      readiness("READY", "s".repeat(64)),
    );
    vi.mocked(api.closeAccountingPeriod).mockRejectedValue(
      new Error("RESOURCE_STATE_CONFLICT"),
    );
    const { result } = renderHook(() => useGovernedPeriodClose(), { wrapper });
    await expect(
      act(async () =>
        result.current.mutateAsync({
          periodId: "period-1",
          expectedVersion: 4,
          reason: "Reviewed close",
        }),
      ),
    ).rejects.toThrow("RESOURCE_STATE_CONFLICT");
    expect(api.closeAccountingPeriod).toHaveBeenCalledTimes(1);
  });
});
