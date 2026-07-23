import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import { getAppointment } from "./scheduling";

vi.mock("./client", () => ({ apiClient: { get: vi.fn() } }));

describe("Scheduling API", () => {
  beforeEach(() => vi.clearAllMocks());
  it("loads Appointment detail from the canonical Scheduling endpoint", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { id: "appointment-1" } });
    await getAppointment("appointment-1");
    expect(apiClient.get).toHaveBeenCalledWith("/api/v1/scheduling/appointments/appointment-1");
  });
});
