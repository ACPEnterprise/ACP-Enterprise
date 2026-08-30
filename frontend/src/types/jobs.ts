export type JobStatus = "draft" | "ready" | "in_progress" | "paused" | "completed" | "cancelled";
export type JobPriority = "low" | "normal" | "high" | "urgent" | "emergency";
export type JobSortField = "job_number" | "priority" | "status" | "created_at" | "updated_at" | "activated_at" | "started_at" | "completed_at" | "cancelled_at" | "customer_display_name" | "earliest_appointment_start_at";
export type SortDirection = "asc" | "desc";
export type JobPauseReason = "customer_unavailable" | "awaiting_approval" | "awaiting_material" | "safety_condition" | "weather" | "operational_hold";
export type JobCancellationReason = "customer_cancelled" | "duplicate" | "created_in_error" | "scope_declined" | "unable_to_perform";
export type JobReopeningReason = "additional_work_required" | "incomplete_work" | "correction_required" | "customer_callback" | "administrative_correction";

export interface JobListParams {
  searchText?: string; status?: readonly JobStatus[]; priority?: readonly JobPriority[];
  jobType?: readonly string[]; branchId?: string; page?: number; pageSize?: number;
  sortField?: JobSortField; sortDirection?: SortDirection;
  appointmentId?: string;
  customerId?: string;
}
export interface JobCreateInput { branch_id: string; customer_id: string; service_location_id: string; job_type_code?: string | null; priority?: JobPriority; customer_reported_problem?: string | null; internal_description?: string | null; }
export interface JobCreateFromAppointmentInput extends Omit<JobCreateInput, "branch_id" | "customer_id" | "service_location_id"> { appointment_id: string; }
export interface JobVersionInput { expected_version: number; }
export interface JobMutationResponse extends Omit<JobCreateInput, "priority"> { id: string; job_number: string; company_id: string; status: JobStatus; priority: JobPriority; concurrency_version: number; activated_at: string | null; started_at: string | null; paused_at: string | null; pause_reason_code: JobPauseReason | null; completed_at: string | null; completed_by_user_id: string | null; cancelled_at: string | null; cancelled_by_user_id: string | null; cancellation_reason_code: JobCancellationReason | null; created_at: string; created_by_user_id: string | null; updated_at: string; updated_by_user_id: string | null; }
export interface JobListItem { id: string; job_number: string; branch_id: string; customer_id: string; customer_display_name: string; service_location_id: string; service_location_label: string; status: JobStatus; priority: JobPriority; job_type_code: string | null; customer_reported_problem_summary: string | null; appointment_count: number; earliest_appointment_start_at: string | null; created_at: string; updated_at: string; started_at: string | null; completed_at: string | null; concurrency_version: number; }
export interface PaginatedJobs { items: readonly JobListItem[]; page: number; page_size: number; total_count: number; total_pages: number; }
export interface JobCustomerSummary { id: string; customer_number: string; display_name: string; }
export interface JobServiceLocationSummary { id: string; nickname: string | null; address_line_1: string; address_line_2: string | null; city: string; state: string; postal_code: string; country: string; }
export interface JobAppointmentSummary { appointment_id: string; visit_sequence: number; appointment_number: string; status: string; arrival_window_start_at: string | null; arrival_window_end_at: string | null; expected_duration_minutes: number | null; }
export interface JobDetail extends JobMutationResponse { customer: JobCustomerSummary; service_location: JobServiceLocationSummary; appointments: readonly JobAppointmentSummary[]; }
