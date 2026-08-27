export const TECHNICIAN_PERMISSION = "COMPANY_JOB_EXECUTE";

export type TechnicianAssignmentStatus =
  | "assigned"
  | "acknowledged"
  | "reconciliation_required";

export type TechnicianArrivalState = "pending" | "en_route" | "arrived";

export interface TechnicianItineraryItem {
  readonly appointment_id: string;
  readonly appointment_number: string;
  readonly job_id: string | null;
  readonly job_number: string | null;
  readonly job_status: "ready" | "in_progress" | "paused" | "completed" | string | null;
  readonly job_version: number | null;
  readonly customer_display_name: string;
  readonly service_location_label: string;
  readonly window_start_at: string;
  readonly window_end_at: string;
  readonly assignment_status: TechnicianAssignmentStatus;
  readonly assignment_version: number;
  readonly arrival_state: TechnicianArrivalState;
  readonly field_execution_enabled?: boolean;
}

export interface TechnicianItinerary {
  readonly service_date: string;
  readonly technician_display_name: string;
  readonly items: readonly TechnicianItineraryItem[];
}
