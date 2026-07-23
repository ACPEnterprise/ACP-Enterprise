import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import * as schedulingApi from "../api/scheduling";
import { appointmentKeys, useAppointment, useAppointments } from "./useScheduling";

vi.mock("../api/scheduling");

describe("Scheduling hooks", () => {
  it("uses a stable Appointment-owned detail key", async () => {
    vi.mocked(schedulingApi.getAppointment).mockResolvedValue({ id: "appointment-1" } as never);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    const result = renderHook(() => useAppointment("appointment-1"), { wrapper });
    await waitFor(() => expect(result.result.current.isSuccess).toBe(true));
    expect(appointmentKeys.detail("appointment-1")).toEqual(["appointments", "detail", "appointment-1"]);
    expect(schedulingApi.getAppointment).toHaveBeenCalledWith("appointment-1");
  });
  it("owns date-and-Branch-scoped Appointment list keys", async () => {
    vi.mocked(schedulingApi.listAppointments).mockResolvedValue({ items: [], total_count: 0, page: 1, page_size: 100, start_at: "start", end_at: "end" });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    const query = { startAt: "start", endAt: "end", branchId: "branch-1", page: 1, pageSize: 100 };
    const result = renderHook(() => useAppointments(query), { wrapper });
    await waitFor(() => expect(result.result.current.isSuccess).toBe(true));
    expect(appointmentKeys.list(query)).toEqual(["appointments", "list", query]);
    expect(schedulingApi.listAppointments).toHaveBeenCalledWith(query);
  });
});
