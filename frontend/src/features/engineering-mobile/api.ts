import { apiClient } from "../../api/client";
import type {
  MobileReviewApproval,
  MobileReviewCancellation,
  MobileReviewDetail,
  MobileReviewQuery,
  MobileCommandStatus,
  MobileOwnerReviewPage,
  MobileWorkstreamPage,
} from "./types";

export const MOBILE_ENGINEERING_PATH = "/api/v1/engineering/mobile/reviews";
export const MOBILE_OWNER_REVIEWS_PATH =
  "/api/v1/engineering/mobile/owner-reviews";
export const MOBILE_WORKSTREAMS_PATH =
  "/api/v1/engineering/mobile/workstreams";

export async function listMobileWorkstreams(
  query: MobileReviewQuery,
): Promise<MobileWorkstreamPage> {
  return (
    await apiClient.get<MobileWorkstreamPage>(MOBILE_WORKSTREAMS_PATH, {
      params: {
        page: query.page,
        page_size: query.pageSize,
      },
    })
  ).data;
}

export async function listMobileReviews(
  query: MobileReviewQuery,
): Promise<MobileOwnerReviewPage> {
  return (
    await apiClient.get<MobileOwnerReviewPage>(MOBILE_OWNER_REVIEWS_PATH, {
      params: {
        page: query.page,
        page_size: query.pageSize,
      },
    })
  ).data;
}

export async function getMobileCommandStatus(
  commandId: string,
): Promise<MobileCommandStatus> {
  return (
    await apiClient.get<MobileCommandStatus>(
      `/api/v1/engineering/mobile/commands/${commandId}/status`,
    )
  ).data;
}

export async function getMobileReview(
  reviewId: string,
): Promise<MobileReviewDetail> {
  return (
    await apiClient.get<MobileReviewDetail>(
      `${MOBILE_ENGINEERING_PATH}/${reviewId}`,
    )
  ).data;
}

export async function approveMobileReview(
  reviewId: string,
  approval: MobileReviewApproval,
): Promise<MobileReviewDetail> {
  return (
    await apiClient.post<MobileReviewDetail>(
      `${MOBILE_ENGINEERING_PATH}/${reviewId}/approve`,
      approval,
    )
  ).data;
}

export async function cancelMobileReview(
  reviewId: string,
  cancellation: MobileReviewCancellation,
): Promise<MobileReviewDetail> {
  return (
    await apiClient.post<MobileReviewDetail>(
      `${MOBILE_ENGINEERING_PATH}/${reviewId}/cancel`,
      cancellation,
    )
  ).data;
}
