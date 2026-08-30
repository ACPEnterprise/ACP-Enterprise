import { apiClient } from "./client";
import type { AppointmentCancelInput, AppointmentCreateInput, AppointmentDetail, AppointmentListParams, AppointmentRescheduleInput, CalendarQueryResult } from "../types/scheduling";

const APPOINTMENTS_PATH = "/api/v1/scheduling/appointments";

export async function getAppointment(appointmentId: string): Promise<AppointmentDetail> {
  return (await apiClient.get<AppointmentDetail>(`${APPOINTMENTS_PATH}/${appointmentId}`)).data;
}

export async function createAppointment(input: AppointmentCreateInput): Promise<AppointmentDetail> {
  return (await apiClient.post<AppointmentDetail>(APPOINTMENTS_PATH, input)).data;
}
export async function rescheduleAppointment(id: string, input: AppointmentRescheduleInput): Promise<AppointmentDetail> {
  return (await apiClient.post<AppointmentDetail>(`${APPOINTMENTS_PATH}/${id}/reschedule`, input)).data;
}
export async function cancelAppointment(id: string, input: AppointmentCancelInput): Promise<AppointmentDetail> {
  return (await apiClient.post<AppointmentDetail>(`${APPOINTMENTS_PATH}/${id}/cancel`, input)).data;
}

export async function listAppointments(query: AppointmentListParams): Promise<CalendarQueryResult> {
  return (await apiClient.get<CalendarQueryResult>(APPOINTMENTS_PATH, { params: {
    start_at: query.startAt,
    end_at: query.endAt,
    branch_id: query.branchId,
    status: query.status,
    page: query.page,
      page_size: query.pageSize,
      customer_id: query.customerId,
  } })).data;
}
