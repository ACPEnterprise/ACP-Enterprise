import type { JobPriority } from "./jobs";
import type { DispatchAssignment } from "./dispatch";
import type { AppointmentDetail } from "./scheduling";

export type SchedulingOverrideReason =
  | "emergency_service"
  | "customer_requested"
  | "dispatcher_override"
  | "owner_override"
  | "after_hours_call"
  | "other";

export interface ServiceRequestCreateInput {
  request_id: string;
  branch_id: string;
  customer_id: string;
  service_location_id: string;
  arrival_window_start_at: string;
  arrival_window_end_at: string;
  expected_duration_minutes: number;
  capacity_units: string;
  job_type_code: string | null;
  priority: JobPriority;
  customer_reported_problem: string | null;
  internal_description: string | null;
}

export interface ServiceRequestResult {
  request_id: string;
  appointment: { id: string; appointment_number: string };
  job: { id: string; job_number: string };
}

export interface ExistingJobScheduleInput {
  request_id: string;
  expected_job_version: number;
  branch_id: string;
  customer_id: string;
  service_location_id: string;
  arrival_window_start_at: string;
  arrival_window_end_at: string;
  expected_duration_minutes: number;
  capacity_units: string;
  reserve_capacity: boolean;
  employee_id: string | null;
  override_reason_code?: SchedulingOverrideReason | null;
}

export interface ExistingJobScheduleResult {
  request_id: string;
  appointment: { id: string; appointment_number: string };
  job: { id: string; job_number: string };
}

export interface CalendarPlacementInput {
  request_id: string;
  expected_appointment_version: number;
  expected_assignment_version: number | null;
  employee_id: string;
  arrival_window_start_at: string;
  arrival_window_end_at: string;
  expected_duration_minutes: number;
  capacity_units: string;
  reason: string;
  override_reason_code?: SchedulingOverrideReason | null;
}

export interface CalendarPlacementResult {
  appointment: AppointmentDetail;
  assignment: DispatchAssignment;
}
