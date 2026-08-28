export interface FieldJobState {
  readonly job_id: string;
  readonly assignment_id: string;
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
