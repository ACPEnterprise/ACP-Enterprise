import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import * as timekeepingApi from "../api/timekeeping";
import { workdayKeys, useApproveTimeEntry, useTimeCorrection } from "./useWorkdayTime";

vi.mock("../api/timekeeping");

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const invalidate = vi.spyOn(client, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, invalidate, wrapper };
}

function expectSupervisorAuthorityRefresh(
  invalidate: ReturnType<typeof vi.spyOn>,
) {
  expect(invalidate).toHaveBeenCalledWith({ queryKey: workdayKeys.adminReview() });
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ["workday", "admin-operations"] });
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ["payroll"] });
}

describe("supervisor timekeeping mutations", () => {
  it("refreshes summary, detailed timecards, and Payroll after a correction", async () => {
    vi.mocked(timekeepingApi.correctTimeEntry).mockResolvedValue({ revision_id: "revision-2" } as never);
    const { invalidate, wrapper } = setup();
    const result = renderHook(() => useTimeCorrection(), { wrapper });

    result.result.current.mutate({
      revisionId: "revision-1",
      input: {
        correction_kind: "missing_clock_out",
        start_at: "2026-11-27T13:00:00Z",
        end_at: "2026-11-27T21:00:00Z",
        approved_duration_minutes: null,
        reason: "Supervisor verified the missed clock-out.",
      },
    });

    await waitFor(() => expect(result.result.current.isSuccess).toBe(true));
    expectSupervisorAuthorityRefresh(invalidate);
  });

  it("reconciles all dependent views after an uncertain approval outcome", async () => {
    vi.mocked(timekeepingApi.approveTimeEntry).mockRejectedValue(new Error("uncertain"));
    const { invalidate, wrapper } = setup();
    const result = renderHook(() => useApproveTimeEntry(), { wrapper });

    result.result.current.mutate("revision-1");

    await waitFor(() => expect(result.result.current.isError).toBe(true));
    expectSupervisorAuthorityRefresh(invalidate);
  });
});
