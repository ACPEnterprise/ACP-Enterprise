import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as jobsApi from "../api/jobs";
import { appointmentKeys } from "./useScheduling";
import { jobKeys, useActivateJob, useCreateJobFromAppointment, useJobs } from "./useJobs";

vi.mock("../api/jobs");

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return { client, wrapper: ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider> };
}

describe("Jobs React Query hooks", () => {
  beforeEach(() => vi.clearAllMocks());
  it("loads Jobs with a stable typed query key", async () => {
    vi.mocked(jobsApi.listJobs).mockResolvedValue({ items: [], page: 1, page_size: 20, total_count: 0, total_pages: 0 });
    const query = { page: 1, pageSize: 20 } as const; const { wrapper } = setup();
    const result = renderHook(() => useJobs(query), { wrapper });
    await waitFor(() => expect(result.result.current.isSuccess).toBe(true));
    expect(jobsApi.listJobs).toHaveBeenCalledWith(query); expect(jobKeys.list(query)).toEqual(["jobs", "list", query]);
  });
  it("invalidates only Jobs lists and the changed detail after lifecycle success", async () => {
    vi.mocked(jobsApi.activateJob).mockResolvedValue({ id: "job-1" } as never);
    const { client, wrapper } = setup(); const invalidate = vi.spyOn(client, "invalidateQueries");
    const result = renderHook(() => useActivateJob("job-1"), { wrapper });
    result.result.current.mutate({ expected_version: 3 });
    await waitFor(() => expect(result.result.current.isSuccess).toBe(true));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: jobKeys.lists() });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: jobKeys.detail("job-1") });
  });
  it("invalidates both domain query families after creating from an Appointment", async () => {
    vi.mocked(jobsApi.createJobFromAppointment).mockResolvedValue({ id: "job-1" } as never);
    const { client, wrapper } = setup(); const invalidate = vi.spyOn(client, "invalidateQueries");
    const result = renderHook(() => useCreateJobFromAppointment("appointment-1"), { wrapper });
    result.result.current.mutate({ priority: "normal" });
    await waitFor(() => expect(result.result.current.isSuccess).toBe(true));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: appointmentKeys.detail("appointment-1") });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: jobKeys.lists() });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: jobKeys.detail("job-1") });
  });
});
