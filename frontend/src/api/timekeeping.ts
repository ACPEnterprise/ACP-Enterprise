import axios from "axios";

import { apiClient } from "./client";

export type PunchAction = "clock_in" | "break_start" | "break_end" | "clock_out";
export type WorkdayStateName = "not_clocked_in" | "clocked_in" | "on_break";

export interface PunchState {
  state: WorkdayStateName;
  last_action: PunchAction | null;
  occurred_at: string | null;
  server_observed_at: string;
  elapsed_seconds: number | null;
}

export interface PayPeriod {
  id: string;
  period_start: string;
  period_end: string;
  processing_date: string;
  payday: string;
  timezone: string;
  schedule_definition_id: string;
  schedule_version: number;
}

export interface TimeEntry {
  entry_id: string;
  revision_id: string;
  revision_number: number;
  work_date: string;
  timezone: string;
  provenance: "employee_punch" | "authorized_manual_entry";
  start_at: string | null;
  end_at: string | null;
  approved_duration_minutes: number | null;
  state: "recorded" | "submitted" | "approved" | "corrected";
  supersedes_revision_id: string | null;
  correction_reason: string | null;
  correction_kind: TimeCorrectionKind | null;
  reviewed_by_user_id: string;
  approved_at: string | null;
}

export type TimeCorrectionKind = "missing_clock_out" | "incorrect_job" | "missing_interval" | "overlapping_intervals" | "incorrect_start" | "incorrect_stop";

export interface TimeCorrectionInput {
  start_at: string | null;
  end_at: string | null;
  approved_duration_minutes: number | null;
  reason: string;
  correction_kind: TimeCorrectionKind;
}

export interface Timecard {
  employee_id: string;
  punch_state: PunchState;
  pay_period: PayPeriod | null;
  entries: TimeEntry[];
  job_intervals: JobWorkedInterval[];
}

export type JobClockAction = "start" | "stop";

export interface JobWorkedInterval {
  interval_id: string;
  revision_id: string;
  revision_number: number;
  employee_id: string;
  job_id: string;
  appointment_id: string | null;
  start_at: string;
  stop_at: string;
  duration_seconds: number;
  source: "employee_clock" | "authorized_manual";
  correction_state: "original" | "corrected" | "superseded";
  supersedes_revision_id: string | null;
  audit_lineage: string[];
  source_event_ids: string[];
  validity: "valid" | "correction_required";
  confidence: "authoritative" | "disputed";
  evidence_digest: string;
  correction_reason: string | null;
}

export interface ActiveJobClock {
  active: boolean;
  event_id: string | null;
  employee_id: string;
  job_id: string | null;
  appointment_id: string | null;
  started_at: string | null;
  server_observed_at: string;
  elapsed_seconds: number | null;
}

export interface JobClockResult {
  event_id: string;
  action: JobClockAction;
  occurred_at: string;
  state: ActiveJobClock;
  completed_interval: JobWorkedInterval | null;
}

export interface PunchResult {
  punch_id: string;
  action: PunchAction;
  occurred_at: string;
  state: PunchState;
  completed_entry: TimeEntry | null;
}

export interface AdminTimecardReviewItem {
  employee_id: string;
  employee_number: string;
  display_name: string;
  home_branch_id: string | null;
  entry_count: number;
  total_minutes: number;
  exception_codes: Array<"no_time" | "unsubmitted" | "corrected" | "overlap">;
  entries: TimeEntry[];
}

export interface AdminTimecardReview {
  pay_period: PayPeriod | null;
  items: AdminTimecardReviewItem[];
}

export interface AdminTimecardInterval {
  entry_id: string;
  revision_id: string;
  revision_number: number;
  work_date: string;
  start_at: string | null;
  end_at: string | null;
  supported_minutes: number;
  job_id: string | null;
  job_number: string | null;
  job_minutes: number | null;
  non_job_supported_minutes: number | null;
  attribution_state: "ATTRIBUTED" | "NON_JOB" | "UNCLASSIFIED";
  provenance: string;
  entry_state: string;
  corrected: boolean;
  overlap: boolean;
  review_state: "ACCEPTED" | "NEEDS_REVIEW";
  audit_digest: string;
}

export interface AdminEmployeeTimecard {
  employee_id: string;
  employee_number: string;
  display_name: string;
  home_branch_id: string | null;
  punch_state: PunchState;
  active_open_clock: boolean;
  missing_clock_out: boolean;
  job_intervals: JobWorkedInterval[];
  days: Array<{
    work_date: string;
    intervals: AdminTimecardInterval[];
    total_supported_minutes: number;
    job_minutes: number | null;
    non_job_supported_minutes: number | null;
    unclassified_minutes: number;
    has_overlap: boolean;
    has_correction: boolean;
    review_state: "ACCEPTED" | "NEEDS_REVIEW";
  }>;
  total_supported_minutes: number;
  accepted_minutes: number;
  exception_codes: string[];
  review_state: "ACCEPTED" | "NEEDS_REVIEW";
}

export interface AdminTimecardOperations {
  contract_version: "WORKFORCE.TIMECARD.OPERATIONS.v1";
  pay_period: PayPeriod;
  employees: AdminEmployeeTimecard[];
  job_attribution_readiness: "AVAILABLE";
  limitations: string[];
}

export type WorkdayAccessFailure =
  | "authentication_required"
  | "permission_denied"
  | "employee_linkage_missing"
  | "conflict"
  | "network_uncertain"
  | "unavailable";

export function classifyWorkdayFailure(error: unknown): WorkdayAccessFailure {
  if (!axios.isAxiosError(error)) return "unavailable";
  if (!error.response) return "network_uncertain";
  if (error.response.status === 401) return "authentication_required";
  if (error.response.status === 403) return "permission_denied";
  if (error.response.status === 409) return "conflict";
  const detail = error.response.data?.detail;
  if (
    error.response.status === 422 &&
    typeof detail === "string" &&
    detail.toLowerCase().includes("employee")
  ) {
    return "employee_linkage_missing";
  }
  return "unavailable";
}

export async function getOwnPunchState(): Promise<PunchState> {
  return (await apiClient.get<PunchState>("/api/v1/timekeeping/me/state")).data;
}

export async function getOwnTimecard(): Promise<Timecard> {
  return (await apiClient.get<Timecard>("/api/v1/timekeeping/me/timecard")).data;
}

export async function recordOwnPunch(
  action: PunchAction,
  idempotencyKey = crypto.randomUUID(),
): Promise<PunchResult> {
  return (
    await apiClient.post<PunchResult>(
      "/api/v1/timekeeping/me/punches",
      { action },
      { headers: { "Idempotency-Key": idempotencyKey } },
    )
  ).data;
}

export async function getAdminTimecardReview(): Promise<AdminTimecardReview> {
  return (
    await apiClient.get<AdminTimecardReview>(
      "/api/v1/timekeeping/admin/timecard-review",
    )
  ).data;
}

export async function getOwnActiveJobClock(): Promise<ActiveJobClock> {
  return (await apiClient.get<ActiveJobClock>("/api/v1/timekeeping/me/job-clock")).data;
}

export async function recordOwnJobClock(
  action: JobClockAction,
  jobId: string,
  appointmentId: string | null,
  idempotencyKey: string,
): Promise<JobClockResult> {
  return (
    await apiClient.post<JobClockResult>(
      "/api/v1/timekeeping/me/job-clock",
      { action, job_id: jobId, appointment_id: appointmentId },
      { headers: { "Idempotency-Key": idempotencyKey } },
    )
  ).data;
}

export async function correctTimeEntry(revisionId: string, input: TimeCorrectionInput): Promise<TimeEntry> {
  return (await apiClient.post<TimeEntry>(
    `/api/v1/timekeeping/entries/${revisionId}/corrections`,
    input,
    { headers: { "Idempotency-Key": crypto.randomUUID() } },
  )).data;
}

export async function getCurrentPayPeriod(): Promise<PayPeriod | null> {
  return (await apiClient.get<PayPeriod | null>("/api/v1/timekeeping/pay-periods/current")).data;
}

export async function getPayPeriods(): Promise<PayPeriod[]> {
  return (await apiClient.get<PayPeriod[]>("/api/v1/timekeeping/pay-periods", { params: { limit: 26 } })).data;
}

export async function getAdminTimecardOperations(payPeriodId: string): Promise<AdminTimecardOperations> {
  return (
    await apiClient.get<AdminTimecardOperations>(
      `/api/v1/timekeeping/admin/pay-periods/${payPeriodId}/timecards`,
    )
  ).data;
}
