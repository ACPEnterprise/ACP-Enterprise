import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import { getAppointment, listAppointments } from "./scheduling";

vi.mock("./client", () => ({ apiClient: { get: vi.fn() } }));

describe("Scheduling API", () => {
  beforeEach(() => vi.clearAllMocks());
  it("loads Appointment detail from the canonical Scheduling endpoint", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { id: "appointment-1" } });
    await getAppointment("appointment-1");
    expect(apiClient.get).toHaveBeenCalledWith("/api/v1/scheduling/appointments/appointment-1");
  });
  it("maps bounded date and Branch scope to the Scheduling query", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { items: [] } });
    await listAppointments({ startAt: "2026-07-23T04:00:00Z", endAt: "2026-07-24T04:00:00Z", branchId: "branch-1", page: 1, pageSize: 100 });
    expect(apiClient.get).toHaveBeenCalledWith("/api/v1/scheduling/appointments", { params: expect.objectContaining({ start_at: "2026-07-23T04:00:00Z", end_at: "2026-07-24T04:00:00Z", branch_id: "branch-1", page_size: 100 }) });
  });
});
