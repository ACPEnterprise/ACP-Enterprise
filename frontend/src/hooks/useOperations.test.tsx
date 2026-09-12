import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import * as operationsApi from "../api/operations";
import { assignPrimary } from "../api/dispatch";
import { jobKeys } from "./useJobs";
import { useCreateServiceRequest, useScheduleExistingJob } from "./useOperations";
import { appointmentKeys } from "./useScheduling";

vi.mock("../api/operations");
vi.mock("../api/dispatch", () => ({ assignPrimary: vi.fn() }));

const request = {
  request_id: "11111111-1111-4111-8111-111111111111",
  branch_id: "branch-1",
  customer_id: "customer-1",
  service_location_id: "location-1",
  arrival_window_start_at: "2026-09-14T13:00:00Z",
  arrival_window_end_at: "2026-09-14T15:00:00Z",
  expected_duration_minutes: 90,
  capacity_units: "1.00",
  job_type_code: null,
  priority: "normal" as const,
  customer_reported_problem: null,
  internal_description: null,
};

const setup = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  return { client, wrapper };
};

describe("Operations recovery", () => {
  it("refreshes queue authority after a failed atomic booking", async () => {
    vi.mocked(operationsApi.createServiceRequest).mockRejectedValue(new Error("uncertain"));
    const { client, wrapper } = setup();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const result = renderHook(() => useCreateServiceRequest(), { wrapper });
    result.result.current.mutate(request);
    await waitFor(() => expect(result.result.current.isError).toBe(true));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: appointmentKeys.lists() });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: jobKeys.lists() });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["dispatch"] });
  });

  it("refreshes the current Job, queue, and Dispatch after stale scheduling fails", async () => {
    vi.mocked(operationsApi.scheduleExistingJob).mockRejectedValue(new Error("stale"));
    const { client, wrapper } = setup();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const result = renderHook(() => useScheduleExistingJob("job-1"), { wrapper });
    result.result.current.mutate({
      ...request,
      expected_job_version: 3,
      reserve_capacity: false,
      employee_id: null,
    });
    await waitFor(() => expect(result.result.current.isError).toBe(true));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: jobKeys.detail("job-1") });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: appointmentKeys.lists() });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["dispatch"] });
  });

  it("binds optional assignment replay to the scheduling request identity", async () => {
    vi.mocked(operationsApi.scheduleExistingJob).mockResolvedValue({
      request_id: request.request_id,
      appointment: { id: "appointment-1", appointment_number: "APT-1" },
      job: { id: "job-1", job_number: "JOB-1" },
    });
    vi.mocked(assignPrimary).mockResolvedValue({ id: "assignment-1" } as never);
    const { wrapper } = setup();
    const result = renderHook(() => useScheduleExistingJob("job-1"), { wrapper });
    result.result.current.mutate({
      ...request,
      expected_job_version: 3,
      reserve_capacity: true,
      employee_id: "employee-1",
    });
    await waitFor(() => expect(result.result.current.isSuccess).toBe(true));
    expect(assignPrimary).toHaveBeenCalledWith(
      "appointment-1",
      "employee-1",
      "Office assignment while scheduling Job",
      undefined,
      `schedule-assignment:${request.request_id}`,
    );
  });
});
