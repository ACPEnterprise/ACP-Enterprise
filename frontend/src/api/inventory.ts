import { apiClient } from "./client";
import type {
  InventoryAllocation,
  InventoryLocation,
  InventoryLocationCreate,
  InventoryOverview,
  InventoryReservation,
  InventoryReservationAllocate,
  InventoryReservationCreate,
  InventoryTransfer,
} from "../types/inventory";

const ROOT = "/api/v1/inventory";

export async function getInventoryOverview(
  branchId?: string,
): Promise<InventoryOverview> {
  return (
    await apiClient.get<InventoryOverview>(`${ROOT}/overview`, {
      params: { branch_id: branchId },
    })
  ).data;
}

export async function createInventoryLocation(
  data: InventoryLocationCreate,
): Promise<InventoryLocation> {
  return (await apiClient.post<InventoryLocation>(`${ROOT}/locations`, data))
    .data;
}

export async function postInventoryTransfer(
  data: InventoryTransfer,
): Promise<void> {
  await apiClient.post(`${ROOT}/transfers`, data);
}

export async function createInventoryReservation(
  data: InventoryReservationCreate,
): Promise<InventoryReservation> {
  return (
    await apiClient.post<InventoryReservation>(`${ROOT}/reservations`, data)
  ).data;
}

export async function allocateInventoryReservation(
  id: string,
  data: InventoryReservationAllocate,
): Promise<InventoryAllocation> {
  return (
    await apiClient.post<InventoryAllocation>(
      `${ROOT}/reservations/${id}/allocations`,
      data,
    )
  ).data;
}

export async function releaseInventoryReservation(
  id: string,
  version: number,
): Promise<void> {
  await apiClient.post(`${ROOT}/reservations/${id}/release`, {
    expected_version: version,
    idempotency_key: crypto.randomUUID(),
  });
}
