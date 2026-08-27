export interface FieldJobState {
  readonly job_id: string;
  readonly assignment_id: string;
  readonly work_summary_recorded: boolean;
  readonly customer_disposition: "approved" | "unavailable" | "refused" | null;
  readonly completion_ready: boolean;
  readonly invoice_handoff_status: "pending" | "completed" | "reconciliation_required" | null;
  readonly invoice_id: string | null;
}

export type CustomerDisposition = "approved" | "unavailable" | "refused";
