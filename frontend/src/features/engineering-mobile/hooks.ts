import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { shouldRetryApiQuery } from "../../api/errors";
import * as mobileApi from "./api";
import type {
  MobileReviewApproval,
  MobileReviewCancellation,
  MobileReviewQuery,
  MobileWorkstreamAction,
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
};

export function useMissionNotifications() {
  return useQuery({
    queryKey: mobileEngineeringKeys.notifications(),
    queryFn: mobileApi.listMissionNotifications,
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
      await queryClient.invalidateQueries({ queryKey: mobileEngineeringKeys.notifications() });
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
    mutationFn: ({ action, reason }: { action: MobileWorkstreamAction; reason?: string }) =>
      mobileApi.controlMobileWorkstream(commandId, action, reason),
    retry: false,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: mobileEngineeringKeys.workstream(commandId) }),
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
