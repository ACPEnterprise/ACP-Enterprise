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
  MilestoneAction,
  MilestoneItem,
  RoadmapPage,
  CapacitySummary,
  CapacityPolicy,
  WorkerCapacity,
  EligibleCapacityWorker,
  CapacityReservation,
  CapacityAllocation,
  CapacityQueueItem,
} from "./types";

export const MOBILE_ENGINEERING_PATH = "/api/v1/engineering/mobile/reviews";
export const MOBILE_OWNER_REVIEWS_PATH =
  "/api/v1/engineering/mobile/owner-reviews";
export const MOBILE_WORKSTREAMS_PATH = "/api/v1/engineering/mobile/workstreams";
export const MISSION_NOTIFICATIONS_PATH =
  "/api/v1/engineering/mobile/notifications";
export const MISSION_ROADMAPS_PATH = "/api/v1/engineering/mobile/roadmaps";
export const ENGINEERING_CAPACITY_PATH = "/api/v1/engineering/capacity";

export async function listMissionNotifications(): Promise<MissionNotificationPage> {
  return (
    await apiClient.get<MissionNotificationPage>(MISSION_NOTIFICATIONS_PATH)
  ).data;
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

export async function listRoadmaps(): Promise<RoadmapPage> {
  return (await apiClient.get<RoadmapPage>(MISSION_ROADMAPS_PATH)).data;
}

export async function actOnMilestone(
  milestoneId: string,
  expectedVersion: number,
  action: MilestoneAction,
  reason?: string,
): Promise<MilestoneItem> {
  return (
    await apiClient.post<MilestoneItem>(
      `/api/v1/engineering/mobile/milestones/${milestoneId}/actions`,
      { expected_version: expectedVersion, action, reason },
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

export async function getCapacitySummary(): Promise<CapacitySummary> {
  return (await apiClient.get<CapacitySummary>(`${ENGINEERING_CAPACITY_PATH}/summary`)).data;
}

export async function updateCapacityPolicy(input: {
  maximum_concurrent_workstreams: number;
  maximum_per_worker: number;
  reserved_capacity: number;
  auto_allocate_released_capacity: boolean;
  expected_version: number | null;
}): Promise<CapacityPolicy> {
  return (await apiClient.put<CapacityPolicy>(`${ENGINEERING_CAPACITY_PATH}/policy`, input)).data;
}

export async function updateWorkerCapacityLimit(worker: WorkerCapacity, configuredLimit: number): Promise<WorkerCapacity> {
  return (await apiClient.put<WorkerCapacity>(`${ENGINEERING_CAPACITY_PATH}/workers/${worker.worker_id}/limit`, {
    configured_limit: configuredLimit,
    expected_version: worker.version,
  })).data;
}

export async function configureExistingWorkerCapacity(input: {
  worker: EligibleCapacityWorker;
  machineLabel: string;
  configuredLimit: number;
}): Promise<WorkerCapacity> {
  return (await apiClient.post<WorkerCapacity>(`${ENGINEERING_CAPACITY_PATH}/workers/configure-existing`, {
    worker_id: input.worker.worker_id,
    machine_label: input.machineLabel,
    configured_limit: input.configuredLimit,
    idempotency_key: `owner-configure-worker:${input.worker.worker_id}`,
  })).data;
}

export async function setWorkerCapacityState(worker: WorkerCapacity, action: "pause" | "restore"): Promise<WorkerCapacity> {
  return (await apiClient.post<WorkerCapacity>(`${ENGINEERING_CAPACITY_PATH}/workers/${worker.worker_id}/${action}`, {
    expected_version: worker.version,
    reason: action === "pause" ? "Owner paused capacity" : "Owner restored capacity",
  })).data;
}

export async function reserveWorkstreamCapacity(item: CapacityQueueItem): Promise<CapacityReservation> {
  return (await apiClient.post<CapacityReservation>(`${ENGINEERING_CAPACITY_PATH}/reservations`, {
    command_id: item.command_id,
    worker_id: item.assigned_worker_id,
    owner_intent_reference: `owner-capacity:${item.command_id}`,
    idempotency_key: `owner-reserve:${item.command_id}`,
    transition_source: "owner",
  })).data;
}

export async function releaseCapacityReservation(reservation: CapacityReservation): Promise<CapacityReservation> {
  return (await apiClient.post<CapacityReservation>(`${ENGINEERING_CAPACITY_PATH}/reservations/${reservation.id}/release`, {
    expected_version: reservation.version,
    reason: "Owner released reservation",
    idempotency_key: `owner-release-reservation:${reservation.id}:${reservation.version}`,
  })).data;
}

export async function releaseCapacityAllocation(allocation: CapacityAllocation): Promise<CapacityAllocation> {
  return (await apiClient.post<CapacityAllocation>(`${ENGINEERING_CAPACITY_PATH}/allocations/${allocation.id}/release`, {
    expected_version: allocation.version,
    reason: "Owner confirmed assignment released",
    idempotency_key: `owner-release-allocation:${allocation.id}:${allocation.version}`,
  })).data;
}

export async function reconcileCapacityAllocation(allocation: CapacityAllocation, resolution: "confirmed_active" | "confirmed_released"): Promise<CapacityAllocation> {
  return (await apiClient.post<CapacityAllocation>(`${ENGINEERING_CAPACITY_PATH}/allocations/${allocation.id}/reconcile`, {
    expected_version: allocation.version,
    resolution,
    reason: resolution === "confirmed_active" ? "Owner confirmed assignment remains active" : "Owner confirmed assignment ended",
    idempotency_key: `owner-reconcile:${allocation.id}:${allocation.version}:${resolution}`,
  })).data;
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

export async function getMobileWorkstream(
  commandId: string,
): Promise<MobileWorkstreamDetail> {
  return (
    await apiClient.get<MobileWorkstreamDetail>(
      `${MOBILE_WORKSTREAMS_PATH}/${commandId}`,
    )
  ).data;
}

export async function controlMobileWorkstream(
  commandId: string,
  action: MobileWorkstreamAction,
  reason?: string,
): Promise<MobileWorkstreamActionResult> {
  return (
    await apiClient.post<MobileWorkstreamActionResult>(
      `${MOBILE_WORKSTREAMS_PATH}/${commandId}/actions`,
      { action, reason },
    )
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
