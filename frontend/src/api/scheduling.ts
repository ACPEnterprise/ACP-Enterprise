import { apiClient } from "./client";
import type { AppointmentDetail } from "../types/scheduling";

const APPOINTMENTS_PATH = "/api/v1/scheduling/appointments";

export async function getAppointment(appointmentId: string): Promise<AppointmentDetail> {
  return (await apiClient.get<AppointmentDetail>(`${APPOINTMENTS_PATH}/${appointmentId}`)).data;
}
