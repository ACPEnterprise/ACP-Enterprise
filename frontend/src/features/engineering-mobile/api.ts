import { apiClient } from "../../api/client";
import type {
  MobileReviewApproval,
  MobileReviewCancellation,
  MobileReviewDetail,
  MobileReviewQuery,
  MobileCommandStatus,
  MobileOwnerReviewPage,
  MobileWorkstreamPage,
  MobileWorkstreamDetail,
  MobileWorkstreamAction,
  MobileWorkstreamActionResult,
  MobileReviewPage,
  MissionNotificationItem,
  MissionNotificationPage,
} from "./types";

export const MOBILE_ENGINEERING_PATH = "/api/v1/engineering/mobile/reviews";
export const MOBILE_OWNER_REVIEWS_PATH =
  "/api/v1/engineering/mobile/owner-reviews";
export const MOBILE_WORKSTREAMS_PATH =
  "/api/v1/engineering/mobile/workstreams";
export const MISSION_NOTIFICATIONS_PATH =
  "/api/v1/engineering/mobile/notifications";

export async function listMissionNotifications(): Promise<MissionNotificationPage> {
  return (await apiClient.get<MissionNotificationPage>(MISSION_NOTIFICATIONS_PATH)).data;
}

export async function acknowledgeMissionNotification(
  notificationId: string,
  expectedVersion: number,
): Promise<MissionNotificationItem> {
  return (
    await apiClient.post<MissionNotificationItem>(
      `${MISSION_NOTIFICATIONS_PATH}/${notificationId}/acknowledge`,
      { expected_version: expectedVersion },
    )
  ).data;
}

export async function transitionMissionNotification(
  notificationId: string,
  expectedVersion: number,
  action: "read" | "archive",
): Promise<MissionNotificationItem> {
  return (
    await apiClient.post<MissionNotificationItem>(
      `${MISSION_NOTIFICATIONS_PATH}/${notificationId}/transition`,
      { expected_version: expectedVersion, action },
    )
  ).data;
}

export async function listPendingMobileReviews(): Promise<MobileReviewPage> {
  return (
    await apiClient.get<MobileReviewPage>(MOBILE_ENGINEERING_PATH, {
      params: { page: 1, page_size: 10 },
    })
  ).data;
}

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

export async function getMobileWorkstream(commandId: string): Promise<MobileWorkstreamDetail> {
  return (await apiClient.get<MobileWorkstreamDetail>(`${MOBILE_WORKSTREAMS_PATH}/${commandId}`)).data;
}

export async function controlMobileWorkstream(commandId: string, action: MobileWorkstreamAction, reason?: string): Promise<MobileWorkstreamActionResult> {
  return (await apiClient.post<MobileWorkstreamActionResult>(`${MOBILE_WORKSTREAMS_PATH}/${commandId}/actions`, { action, reason })).data;
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
