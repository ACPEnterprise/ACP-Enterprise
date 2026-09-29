export type AppointmentStatus =
  "draft" | "scheduled" | "confirmed" | "completed" | "cancelled" | "no_show";

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

export interface AppointmentRescheduleInput {
  expected_version: number;
  arrival_window_start_at: string;
  arrival_window_end_at: string;
  expected_duration_minutes: number;
  capacity_units: string;
  reason_code:
    | "customer_request"
    | "operational_adjustment"
    | "scheduling_conflict"
    | "weather";
}

export interface BranchWeeklyInterval {
  day_of_week: number;
  start_minute: number;
  end_minute: number;
  capacity_units: string;
}

export interface BranchSchedulingException {
  exception_date: string;
  start_minute: number | null;
  end_minute: number | null;
  is_closed: boolean;
  capacity_units: string | null;
  reason_code: string;
}

export interface BranchSchedulingPolicy {
  branch_id: string;
  timezone: string;
  status: "NOT_CONFIGURED" | "ACTIVE" | "INACTIVE";
  readiness: "SCHEDULING_READY" | "SCHEDULING_SETUP_REQUIRED";
  blockers: string[];
  version: number | null;
  booking_horizon_days: number | null;
  minimum_notice_minutes: number | null;
  slot_interval_minutes: number | null;
  default_capacity_units: string | null;
  weekly_intervals: BranchWeeklyInterval[];
  exceptions: BranchSchedulingException[];
}

export interface BranchSchedulingPolicyInput {
  expected_version: number | null;
  timezone: string;
  active: boolean;
  booking_horizon_days: number;
  minimum_notice_minutes: number;
  slot_interval_minutes: number;
  default_capacity_units: string;
  weekly_intervals: BranchWeeklyInterval[];
  exceptions: BranchSchedulingException[];
  reason: string;
}

export interface BranchCalendarTechnician {
  employee_id: string;
  employee_number: string;
  display_name: string;
  job_title: string | null;
  readiness: "AVAILABLE" | "UNAVAILABLE" | "READINESS_BLOCKED";
  readiness_reasons: string[];
  availability_confidence: string;
}

export interface BranchCalendarRoster {
  branch_id: string;
  window_start_at: string;
  window_end_at: string;
  technicians: BranchCalendarTechnician[];
}
