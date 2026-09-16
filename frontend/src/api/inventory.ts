import { apiClient } from "./client";
import type {
  InventoryAllocation,
  CycleCountRecord,
  CycleCountSession,
  CycleCountStart,
  InventoryAdjustment,
  InventoryAdjustmentCreate,
  InventoryLocation,
  InventoryItem,
  InventoryItemCreate,
  InventoryLocationCreate,
  JobMaterials,
  InventoryOverview,
  InventoryMaterialIssue,
  InventoryMaterialIssueCreate,
  InventoryMaterialIssueReverse,
  InventoryReservation,
  InventoryReservationAllocate,
  InventoryReservationCreate,
  InventoryTransfer,
  MaterialCostReadiness,
} from "../types/inventory";

const ROOT = "/api/v1/inventory";

export async function getJobMaterials(jobId: string): Promise<JobMaterials> {
  return (
    await apiClient.get<JobMaterials>(
      `${ROOT}/jobs/${encodeURIComponent(jobId)}/materials`,
    )
  ).data;
}

export async function getMaterialCostReadiness(): Promise<MaterialCostReadiness> {
  return (await apiClient.get<MaterialCostReadiness>(`${ROOT}/cost-readiness`)).data;
}

export async function getInventoryOverview(
  branchId?: string,
): Promise<InventoryOverview> {
  return (
    await apiClient.get<InventoryOverview>(`${ROOT}/overview`, {
      params: { branch_id: branchId },
    })
  ).data;
}

export async function createInventoryItem(
  data: InventoryItemCreate,
): Promise<InventoryItem> {
  const { code, ...body } = data;
  return (
    await apiClient.put<InventoryItem>(
      `${ROOT}/items/${encodeURIComponent(code.trim().toUpperCase())}`,
      body,
    )
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

export async function issueInventoryMaterial(
  reservationId: string,
  data: InventoryMaterialIssueCreate,
): Promise<InventoryMaterialIssue> {
  return (
    await apiClient.post<InventoryMaterialIssue>(
      `${ROOT}/reservations/${reservationId}/issues`,
      data,
    )
  ).data;
}

export async function reverseInventoryMaterialIssue(
  issueId: string,
  data: InventoryMaterialIssueReverse,
): Promise<InventoryMaterialIssue> {
  return (
    await apiClient.post<InventoryMaterialIssue>(
      `${ROOT}/material-issues/${issueId}/reversal`,
      data,
    )
  ).data;
}

export async function postInventoryAdjustment(
  data: InventoryAdjustmentCreate,
): Promise<InventoryAdjustment> {
  return (
    await apiClient.post<InventoryAdjustment>(`${ROOT}/adjustments`, data)
  ).data;
}

export async function getCycleCounts(
  branchId?: string,
): Promise<readonly CycleCountSession[]> {
  return (
    await apiClient.get<readonly CycleCountSession[]>(`${ROOT}/cycle-counts`, {
      params: { branch_id: branchId },
    })
  ).data;
}

export async function startCycleCount(
  data: CycleCountStart,
): Promise<CycleCountSession> {
  return (await apiClient.post<CycleCountSession>(`${ROOT}/cycle-counts`, data))
    .data;
}

export async function recordCycleCount(
  id: string,
  data: CycleCountRecord,
): Promise<void> {
  await apiClient.post(`${ROOT}/cycle-counts/${id}/entries`, data);
}

export async function completeCycleCount(
  id: string,
  version: number,
): Promise<CycleCountSession> {
  return (
    await apiClient.post<CycleCountSession>(
      `${ROOT}/cycle-counts/${id}/complete`,
      {
        expected_version: version,
      },
    )
  ).data;
}
