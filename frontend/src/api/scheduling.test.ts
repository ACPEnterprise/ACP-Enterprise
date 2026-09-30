import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import {
  getAppointment,
  getBranchCalendarRoster,
  listAppointments,
  rescheduleAppointment,
} from "./scheduling";

vi.mock("./client", () => ({ apiClient: { get: vi.fn(), post: vi.fn() } }));

describe("Scheduling API", () => {
  beforeEach(() => vi.clearAllMocks());
  it("loads Appointment detail from the canonical Scheduling endpoint", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: { id: "appointment-1" },
    });
    await getAppointment("appointment-1");
    expect(apiClient.get).toHaveBeenCalledWith(
      "/api/v1/scheduling/appointments/appointment-1",
    );
  });

  it("reschedules through the versioned Scheduling mutation", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: { id: "appointment-1" },
    });
    const input = {
      expected_version: 4,
      arrival_window_start_at: "2026-09-02T13:00:00Z",
      arrival_window_end_at: "2026-09-02T14:30:00Z",
      expected_duration_minutes: 90,
      capacity_units: "1.00",
      reason_code: "operational_adjustment" as const,
    };
    await rescheduleAppointment("appointment-1", input);
    expect(apiClient.post).toHaveBeenCalledWith(
      "/api/v1/scheduling/appointments/appointment-1/reschedule",
      input,
    );
  });
  it("loads the Branch calendar roster through Scheduling read authority", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { technicians: [] } });
    await getBranchCalendarRoster("branch-1", "2026-09-02T00:00:00Z", "2026-09-03T00:00:00Z");
    expect(apiClient.get).toHaveBeenCalledWith(
      "/api/v1/scheduling/branches/branch-1/calendar-roster",
      { params: { start_at: "2026-09-02T00:00:00Z", end_at: "2026-09-03T00:00:00Z" } },
    );
  });
  it("maps bounded date and Branch scope to the Scheduling query", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { items: [] } });
    await listAppointments({
      startAt: "2026-07-23T04:00:00Z",
      endAt: "2026-07-24T04:00:00Z",
      branchId: "branch-1",
      page: 1,
      pageSize: 100,
    });
    expect(apiClient.get).toHaveBeenCalledWith(
      "/api/v1/scheduling/appointments",
      {
        params: expect.objectContaining({
          start_at: "2026-07-23T04:00:00Z",
          end_at: "2026-07-24T04:00:00Z",
          branch_id: "branch-1",
          page_size: 100,
        }),
      },
    );
  });
});
