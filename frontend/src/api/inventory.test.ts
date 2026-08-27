import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import {
  allocateInventoryReservation,
  createInventoryLocation,
  createInventoryReservation,
} from "./inventory";

vi.mock("./client", () => ({ apiClient: { get: vi.fn(), post: vi.fn() } }));

describe("Inventory API", () => {
  beforeEach(() => vi.clearAllMocks());

  it("uses the accepted location and reservation endpoints", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { id: "result-1" } });

    await createInventoryLocation({
      branch_id: "branch-1",
      code: "MAIN",
      name: "Main warehouse",
      location_type: "warehouse",
    });
    expect(apiClient.post).toHaveBeenLastCalledWith(
      "/api/v1/inventory/locations",
      expect.objectContaining({ branch_id: "branch-1", code: "MAIN" }),
    );

    await createInventoryReservation({
      branch_id: "branch-1",
      item_id: "item-1",
      location_id: "location-1",
      quantity: "2",
      demand_type: "job",
      demand_id: "00000000-0000-0000-0000-000000000001",
      idempotency_key: "reserve-1",
    });
    expect(apiClient.post).toHaveBeenLastCalledWith(
      "/api/v1/inventory/reservations",
      expect.objectContaining({ idempotency_key: "reserve-1" }),
    );

    await allocateInventoryReservation("reservation-1", {
      quantity: null,
      allow_partial: true,
      expected_version: 2,
      idempotency_key: "allocate-1",
    });
    expect(apiClient.post).toHaveBeenLastCalledWith(
      "/api/v1/inventory/reservations/reservation-1/allocations",
      expect.objectContaining({ expected_version: 2, allow_partial: true }),
    );
  });
});
