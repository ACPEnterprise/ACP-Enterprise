import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import { getTechnicianItinerary } from "./technician";

vi.mock("./client", () => ({ apiClient: { get: vi.fn() } }));

describe("technician API", () => {
  beforeEach(() => vi.clearAllMocks());

  it("requests only the authenticated technician's service-day projection", async () => {
    const data = {
      service_date: "2026-08-26",
      technician_display_name: "Alex Rivera",
      items: [],
    };
    vi.mocked(apiClient.get).mockResolvedValue({ data });

    await expect(getTechnicianItinerary("2026-08-26")).resolves.toBe(data);
    expect(apiClient.get).toHaveBeenCalledWith("/api/v1/technician/itinerary", {
      params: { service_date: "2026-08-26" },
    });
  });
});
