export interface FieldJobState {
  readonly job_id: string;
  readonly assignment_id: string;
  readonly appointment_id: string;
  readonly job_number: string;
  readonly job_status: string;
  readonly job_type_code: string | null;
  readonly priority: string;
  readonly customer_display_name: string;
  readonly contact_display_name: string | null;
  readonly contact_phone: string | null;
  readonly contact_email: string | null;
  readonly service_location_label: string;
  readonly customer_reported_problem: string | null;
  readonly internal_description: string | null;
  readonly window_start_at: string | null;
  readonly window_end_at: string | null;
  readonly job_version: number;
  readonly appointment_version: number;
  readonly active_activity: "working" | "parts_run" | null;
  readonly visit_finished: boolean;
  readonly work_summary_recorded: boolean;
  readonly customer_disposition: "approved" | "unavailable" | "refused" | null;
  readonly completion_ready: boolean;
  readonly requirement_snapshot_version: number | null;
  readonly missing_requirements: readonly string[];
  readonly commercial_authorization: "accepted_estimate" | "non_billable" | "missing";
  readonly non_billable_reason: string | null;
  readonly invoice_handoff_status: "pending" | "completed" | "reconciliation_required" | null;
  readonly invoice_id: string | null;
}

export type CustomerDisposition = "approved" | "unavailable" | "refused";
