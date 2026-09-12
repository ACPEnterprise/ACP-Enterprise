import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import * as schedulingApi from "../api/scheduling";
import { appointmentKeys, useAppointment, useAppointments, useRescheduleAppointment } from "./useScheduling";

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
  it("refreshes Schedule, Appointment detail, and Dispatch after a confirmed reschedule", async () => {
    vi.mocked(schedulingApi.rescheduleAppointment).mockResolvedValue({ id: "appointment-1" } as never);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    const result = renderHook(() => useRescheduleAppointment(), { wrapper });
    result.result.current.mutate({
      appointmentId: "appointment-1",
      input: {
        expected_version: 2,
        arrival_window_start_at: "2026-08-13T14:00:00Z",
        arrival_window_end_at: "2026-08-13T16:00:00Z",
        expected_duration_minutes: 120,
        capacity_units: "1.000",
        reason_code: "operational_adjustment",
      },
    });
    await waitFor(() => expect(result.result.current.isSuccess).toBe(true));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: appointmentKeys.lists() });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: appointmentKeys.detail("appointment-1") });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["dispatch"] });
  });
  it("refreshes authoritative projections after a failed or uncertain reschedule", async () => {
    vi.mocked(schedulingApi.rescheduleAppointment).mockRejectedValue(new Error("uncertain"));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    const result = renderHook(() => useRescheduleAppointment(), { wrapper });
    result.result.current.mutate({
      appointmentId: "appointment-1",
      input: {
        expected_version: 2,
        arrival_window_start_at: "2026-08-13T14:00:00Z",
        arrival_window_end_at: "2026-08-13T16:00:00Z",
        expected_duration_minutes: 120,
        capacity_units: "1.000",
        reason_code: "operational_adjustment",
      },
    });
    await waitFor(() => expect(result.result.current.isError).toBe(true));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: appointmentKeys.lists() });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: appointmentKeys.detail("appointment-1") });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["dispatch"] });
  });
});
