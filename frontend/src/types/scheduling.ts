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

export interface AppointmentListParams {
  startAt: string;
  endAt: string;
  branchId?: string;
  status?: readonly AppointmentStatus[];
  page?: number;
  pageSize?: number;
  customerId?: string;
}

export interface CalendarQueryResult {
  items: readonly AppointmentDetail[];
  total_count: number;
  page: number;
  page_size: number;
  start_at: string;
  end_at: string;
}

export interface AppointmentCreateInput {
  branch_id: string; customer_id: string; service_location_id: string;
  arrival_window_start_at: string; arrival_window_end_at: string;
  expected_duration_minutes: number; capacity_units: string; idempotency_key: string;
}
export interface AppointmentRescheduleInput {
  expected_version: number; arrival_window_start_at: string; arrival_window_end_at: string;
  expected_duration_minutes: number; capacity_units: string;
  reason_code: "customer_request" | "technician_unavailable" | "weather" | "operational_conflict" | "scope_change";
}
export interface AppointmentCancelInput {
  expected_version: number;
  reason_code: "customer_request" | "duplicate" | "created_in_error" | "unable_to_service" | "weather";
}
