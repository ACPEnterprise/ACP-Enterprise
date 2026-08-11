import { apiClient } from "./client";
import type { InventoryOverview, InventoryTransfer } from "../types/inventory";

const ROOT = "/api/v1/inventory";

export async function getInventoryOverview(branchId?: string): Promise<InventoryOverview> {
  return (await apiClient.get<InventoryOverview>(`${ROOT}/overview`, { params: { branch_id: branchId } })).data;
}

export async function postInventoryTransfer(data: InventoryTransfer): Promise<void> {
  await apiClient.post(`${ROOT}/transfers`, data);
}

export async function releaseInventoryReservation(id: string, version: number): Promise<void> {
  await apiClient.post(`${ROOT}/reservations/${id}/release`, { expected_version: version, idempotency_key: crypto.randomUUID() });
}
