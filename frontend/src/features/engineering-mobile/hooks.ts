import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { shouldRetryApiQuery } from "../../api/errors";
import * as mobileApi from "./api";
import type {
  CapacityAllocation,
  CapacityReservation,
  CapacityQueueItem,
  WorkerCapacity,
  EligibleCapacityWorker,
  MobileReviewApproval,
  MobileReviewCancellation,
  MobileReviewQuery,
  MobileWorkstreamAction,
  MilestoneAction,
} from "./types";

export const mobileEngineeringKeys = {
  all: ["engineering-mobile"] as const,
  lists: () => ["engineering-mobile", "list"] as const,
  list: (query: MobileReviewQuery) =>
    ["engineering-mobile", "list", query] as const,
  workstreams: (query: MobileReviewQuery) =>
    ["engineering-mobile", "workstreams", query] as const,
  detail: (reviewId: string) =>
    ["engineering-mobile", "detail", reviewId] as const,
  status: (reviewId: string) =>
    ["engineering-mobile", "status", reviewId] as const,
  workstream: (commandId: string) =>
    ["engineering-mobile", "workstream", commandId] as const,
  notifications: () => ["engineering-mobile", "notifications"] as const,
  approvalQueue: () => ["engineering-mobile", "approval-queue"] as const,
  roadmaps: () => ["engineering-mobile", "roadmaps"] as const,
  capacity: () => ["engineering-mobile", "capacity"] as const,
};

export function useMissionNotifications() {
  return useQuery({
    queryKey: mobileEngineeringKeys.notifications(),
    queryFn: mobileApi.listMissionNotifications,
    retry: shouldRetryApiQuery,
  });
}

export function useEngineeringCapacity() {
  return useQuery({
    queryKey: mobileEngineeringKeys.capacity(),
    queryFn: mobileApi.getCapacitySummary,
    retry: shouldRetryApiQuery,
  });
}

export function useAcknowledgeMissionNotification() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, version }: { id: string; version: number }) =>
      mobileApi.acknowledgeMissionNotification(id, version),
    retry: false,
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: mobileEngineeringKeys.notifications(),
      });
    },
  });
}

export function useCapacityMutation<T>(mutationFn: (input: T) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    retry: false,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: mobileEngineeringKeys.capacity() });
    },
  });
}

export function useTransitionMissionNotification() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      version,
      action,
    }: {
      id: string;
      version: number;
      action: "read" | "archive";
    }) => mobileApi.transitionMissionNotification(id, version, action),
    retry: false,
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: mobileEngineeringKeys.notifications(),
      });
    },
  });
}

export function usePendingMobileReviews() {
  return useQuery({
    queryKey: mobileEngineeringKeys.approvalQueue(),
    queryFn: mobileApi.listPendingMobileReviews,
    retry: shouldRetryApiQuery,
  });
}

export function useRoadmaps() {
  return useQuery({
    queryKey: mobileEngineeringKeys.roadmaps(),
    queryFn: mobileApi.listRoadmaps,
    retry: shouldRetryApiQuery,
  });
}

export function useMilestoneAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      version,
      action,
      reason,
    }: {
      id: string;
      version: number;
      action: MilestoneAction;
      reason?: string;
    }) => mobileApi.actOnMilestone(id, version, action, reason),
    retry: false,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: mobileEngineeringKeys.roadmaps(),
        }),
        queryClient.invalidateQueries({ queryKey: mobileEngineeringKeys.all }),
      ]);
    },
  });
}

export function useWorkerLimitMutation() {
  return useCapacityMutation<{ worker: WorkerCapacity; limit: number }>(({ worker, limit }) => mobileApi.updateWorkerCapacityLimit(worker, limit));
}

export function useExistingWorkerSetupMutation() {
  return useCapacityMutation<{
    worker: EligibleCapacityWorker;
    machineLabel: string;
    configuredLimit: number;
  }>(mobileApi.configureExistingWorkerCapacity);
}

export function useWorkerStateMutation() {
  return useCapacityMutation<{ worker: WorkerCapacity; action: "pause" | "restore" }>(({ worker, action }) => mobileApi.setWorkerCapacityState(worker, action));
}

export function useReservationMutation() {
  return useCapacityMutation<CapacityQueueItem>(mobileApi.reserveWorkstreamCapacity);
}

export function useReservationReleaseMutation() {
  return useCapacityMutation<CapacityReservation>(mobileApi.releaseCapacityReservation);
}

export function useAllocationReleaseMutation() {
  return useCapacityMutation<CapacityAllocation>(mobileApi.releaseCapacityAllocation);
}

export function useAllocationReconciliationMutation() {
  return useCapacityMutation<{ allocation: CapacityAllocation; resolution: "confirmed_active" | "confirmed_released" }>(({ allocation, resolution }) => mobileApi.reconcileCapacityAllocation(allocation, resolution));
}

export function useMobileWorkstreams(query: MobileReviewQuery) {
  return useQuery({
    queryKey: mobileEngineeringKeys.workstreams(query),
    queryFn: () => mobileApi.listMobileWorkstreams(query),
    retry: shouldRetryApiQuery,
  });
}

export function useMobileWorkstream(commandId: string | undefined) {
  return useQuery({
    queryKey: mobileEngineeringKeys.workstream(commandId ?? ""),
    queryFn: () => mobileApi.getMobileWorkstream(commandId as string),
    enabled: Boolean(commandId),
    retry: shouldRetryApiQuery,
  });
}

export function useControlMobileWorkstream(commandId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      action,
      reason,
    }: {
      action: MobileWorkstreamAction;
      reason?: string;
    }) => mobileApi.controlMobileWorkstream(commandId, action, reason),
    retry: false,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: mobileEngineeringKeys.workstream(commandId),
        }),
        queryClient.invalidateQueries({ queryKey: mobileEngineeringKeys.all }),
      ]);
    },
  });
}

export function useMobileReviews(query: MobileReviewQuery) {
  return useQuery({
    queryKey: mobileEngineeringKeys.list(query),
    queryFn: () => mobileApi.listMobileReviews(query),
    retry: shouldRetryApiQuery,
  });
}

export function useMobileCommandStatus(reviewId: string | undefined) {
  return useQuery({
    queryKey: mobileEngineeringKeys.status(reviewId ?? ""),
    queryFn: () => mobileApi.getMobileCommandStatus(reviewId as string),
    enabled: Boolean(reviewId),
    retry: shouldRetryApiQuery,
  });
}

export function useMobileReview(reviewId: string | undefined) {
  return useQuery({
    queryKey: mobileEngineeringKeys.detail(reviewId ?? ""),
    queryFn: () => mobileApi.getMobileReview(reviewId as string),
    enabled: Boolean(reviewId),
    retry: shouldRetryApiQuery,
  });
}

function useReviewMutation<T>(
  reviewId: string,
  mutationFn: (input: T) => Promise<{ id: string }>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    retry: false,
    onSettled: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: mobileEngineeringKeys.lists(),
        }),
        queryClient.invalidateQueries({
          queryKey: mobileEngineeringKeys.detail(reviewId),
        }),
        queryClient.invalidateQueries({
          queryKey: mobileEngineeringKeys.status(reviewId),
        }),
      ]);
    },
  });
}

export function useApproveMobileReview(reviewId: string) {
  return useReviewMutation<MobileReviewApproval>(reviewId, (approval) =>
    mobileApi.approveMobileReview(reviewId, approval),
  );
}

export function useCancelMobileReview(reviewId: string) {
  return useReviewMutation<MobileReviewCancellation>(reviewId, (cancellation) =>
    mobileApi.cancelMobileReview(reviewId, cancellation),
  );
}
