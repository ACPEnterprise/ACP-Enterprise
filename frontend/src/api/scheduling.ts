import { apiClient } from "./client";
import type {
  AppointmentDetail,
  AppointmentListParams,
  AppointmentRescheduleInput,
  CalendarQueryResult,
  BranchSchedulingPolicy,
  BranchSchedulingPolicyInput,
  BranchCalendarRoster,
} from "../types/scheduling";

const APPOINTMENTS_PATH = "/api/v1/scheduling/appointments";

export async function getBranchSchedulingPolicy(branchId: string) {
  return (
    await apiClient.get<BranchSchedulingPolicy>(
      `/api/v1/scheduling/branches/${branchId}/policy`,
    )
  ).data;
}

export async function getBranchCalendarRoster(branchId: string, startAt: string, endAt: string) {
  return (
    await apiClient.get<BranchCalendarRoster>(
      `/api/v1/scheduling/branches/${branchId}/calendar-roster`,
      { params: { start_at: startAt, end_at: endAt } },
    )
  ).data;
}

export async function configureBranchSchedulingPolicy(
  branchId: string,
  input: BranchSchedulingPolicyInput,
) {
  return (
    await apiClient.put<BranchSchedulingPolicy>(
      `/api/v1/scheduling/branches/${branchId}/policy`,
      input,
    )
  ).data;
}

export async function getAppointment(
  appointmentId: string,
): Promise<AppointmentDetail> {
  return (
    await apiClient.get<AppointmentDetail>(
      `${APPOINTMENTS_PATH}/${appointmentId}`,
    )
  ).data;
}

export async function rescheduleAppointment(
  appointmentId: string,
  input: AppointmentRescheduleInput,
): Promise<AppointmentDetail> {
  return (
    await apiClient.post<AppointmentDetail>(
      `${APPOINTMENTS_PATH}/${appointmentId}/reschedule`,
      input,
    )
  ).data;
}

export async function listAppointments(
  query: AppointmentListParams,
): Promise<CalendarQueryResult> {
  return (
    await apiClient.get<CalendarQueryResult>(APPOINTMENTS_PATH, {
      params: {
        start_at: query.startAt,
        end_at: query.endAt,
        branch_id: query.branchId,
        status: query.status,
        page: query.page,
        page_size: query.pageSize,
        customer_id: query.customerId,
      },
    })
  ).data;
}
