import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  allocateInventoryReservation,
  completeCycleCount,
  createInventoryLocation,
  createInventoryItem,
  createInventoryReservation,
  getInventoryOverview,
  getJobMaterials,
  getMaterialCostReadiness,
  getCycleCounts,
  issueInventoryMaterial,
  postInventoryAdjustment,
  postInventoryTransfer,
  releaseInventoryReservation,
  reverseInventoryMaterialIssue,
  recordCycleCount,
  startCycleCount,
} from "../api/inventory";
import type {
  CycleCountRecord,
  InventoryReservationAllocate,
  InventoryMaterialIssueCreate,
  InventoryMaterialIssueReverse,
} from "../types/inventory";

const inventoryKeys = {
  all: ["inventory"] as const,
  overview: (branch?: string) => ["inventory", "overview", branch] as const,
  cycleCounts: (branch?: string) =>
    ["inventory", "cycle-counts", branch] as const,
  jobMaterials: (jobId?: string) => ["inventory", "jobs", jobId, "materials"] as const,
  costReadiness: ["inventory", "cost-readiness"] as const,
};

export function useJobMaterials(jobId?: string, enabled = true) {
  return useQuery({
    queryKey: inventoryKeys.jobMaterials(jobId),
    queryFn: () => getJobMaterials(jobId!),
    enabled: enabled && Boolean(jobId),
  });
}

export function useInventory(branch?: string, enabled = true) {
  return useQuery({
    queryKey: inventoryKeys.overview(branch),
    queryFn: () => getInventoryOverview(branch),
    enabled,
  });
}

export function useCycleCounts(branch?: string, enabled = true) {
  return useQuery({
    queryKey: inventoryKeys.cycleCounts(branch),
    queryFn: () => getCycleCounts(branch),
    enabled,
  });
}

export function useMaterialCostReadiness(enabled = true) {
  return useQuery({
    queryKey: inventoryKeys.costReadiness,
    queryFn: getMaterialCostReadiness,
    enabled,
  });
}

export function useInventoryMutations() {
  const client = useQueryClient();
  const refresh = () =>
    client.invalidateQueries({ queryKey: inventoryKeys.all });
  return {
    createItem: useMutation({ mutationFn: createInventoryItem, onSuccess: refresh }),
    createLocation: useMutation({
      mutationFn: createInventoryLocation,
      onSuccess: refresh,
    }),
    transfer: useMutation({
      mutationFn: postInventoryTransfer,
      onSuccess: refresh,
    }),
    createReservation: useMutation({
      mutationFn: createInventoryReservation,
      onSuccess: refresh,
    }),
    allocate: useMutation({
      mutationFn: ({
        id,
        data,
      }: {
        id: string;
        data: InventoryReservationAllocate;
      }) => allocateInventoryReservation(id, data),
      onSuccess: refresh,
    }),
    release: useMutation({
      mutationFn: ({ id, version }: { id: string; version: number }) =>
        releaseInventoryReservation(id, version),
      onSuccess: refresh,
    }),
    issueMaterial: useMutation({
      mutationFn: ({
        reservationId,
        data,
      }: {
        reservationId: string;
        data: InventoryMaterialIssueCreate;
      }) => issueInventoryMaterial(reservationId, data),
      onSuccess: refresh,
    }),
    reverseIssue: useMutation({
      mutationFn: ({
        issueId,
        data,
      }: {
        issueId: string;
        data: InventoryMaterialIssueReverse;
      }) => reverseInventoryMaterialIssue(issueId, data),
      onSuccess: refresh,
    }),
    adjust: useMutation({
      mutationFn: postInventoryAdjustment,
      onSuccess: refresh,
    }),
    startCount: useMutation({
      mutationFn: startCycleCount,
      onSuccess: refresh,
    }),
    recordCount: useMutation({
      mutationFn: ({ id, data }: { id: string; data: CycleCountRecord }) =>
        recordCycleCount(id, data),
      onSuccess: refresh,
    }),
    completeCount: useMutation({
      mutationFn: ({ id, version }: { id: string; version: number }) =>
        completeCycleCount(id, version),
      onSuccess: refresh,
    }),
  };
}
