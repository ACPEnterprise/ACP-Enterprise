import { apiClient } from "./client";
import type {
  AppointmentDetail,
  AppointmentListParams,
  AppointmentRescheduleInput,
  CalendarQueryResult,
} from "../types/scheduling";

const APPOINTMENTS_PATH = "/api/v1/scheduling/appointments";

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
