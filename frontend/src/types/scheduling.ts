export type AppointmentStatus = "draft" | "scheduled" | "confirmed" | "completed" | "cancelled" | "no_show";

export interface AppointmentDetail {
  id: string;
  appointment_number: string;
  company_id: string;
  branch_id: string;
  customer_id: string;
  service_location_id: string;
  status: AppointmentStatus;
  arrival_window_start_at: string | null;
  arrival_window_end_at: string | null;
  expected_duration_minutes: number | null;
  capacity_units: string | null;
  concurrency_version: number;
  reschedule_count: number;
  rescheduled_at: string | null;
  cancelled_at: string | null;
  cancellation_reason_code: string | null;
  created_at: string;
  updated_at: string;
}
