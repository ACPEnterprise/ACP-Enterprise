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
  approved_at: string | null;
}

export interface Timecard {
  employee_id: string;
  punch_state: PunchState;
  pay_period: PayPeriod | null;
  entries: TimeEntry[];
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
  job_attribution_readiness: "PARTIAL";
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

export async function recordOwnPunch(action: PunchAction): Promise<PunchResult> {
  const idempotencyKey = crypto.randomUUID();
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
