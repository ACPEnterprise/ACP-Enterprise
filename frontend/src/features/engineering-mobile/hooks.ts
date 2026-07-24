import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { shouldRetryApiQuery } from "../../api/errors";
import * as mobileApi from "./api";
import type {
  MobileReviewApproval,
  MobileReviewCancellation,
  MobileReviewQuery,
} from "./types";

export const mobileEngineeringKeys = {
  all: ["engineering-mobile"] as const,
  lists: () => ["engineering-mobile", "list"] as const,
  list: (query: MobileReviewQuery) =>
    ["engineering-mobile", "list", query] as const,
  detail: (reviewId: string) =>
    ["engineering-mobile", "detail", reviewId] as const,
  status: (reviewId: string) =>
    ["engineering-mobile", "status", reviewId] as const,
};

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
