import { describe, expect, it, vi } from "vitest";

import { createServiceRequest, placeCalendarAppointment } from "./operations";
import { apiClient } from "./client";

vi.mock("./client", () => ({ apiClient: { post: vi.fn() } }));

describe("operations API", () => {
  it("uses the authoritative atomic service-request endpoint", async () => {
    const input = { request_id: "request-1" } as never;
    vi.mocked(apiClient.post).mockResolvedValue({ data: { request_id: "request-1" } });
    await createServiceRequest(input);
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/operations/service-requests", input);
  });

  it("uses the atomic Calendar placement endpoint", async () => {
    const input = { request_id: "request-2", employee_id: "employee-1" } as never;
    vi.mocked(apiClient.post).mockResolvedValue({ data: {} });
    await placeCalendarAppointment("appointment-1", input);
    expect(apiClient.post).toHaveBeenCalledWith(
      "/api/v1/operations/appointments/appointment-1/calendar-placement",
      input,
    );
  });
});
