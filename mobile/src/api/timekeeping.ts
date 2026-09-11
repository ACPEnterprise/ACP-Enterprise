import { z } from "zod";
import type { ApiClient } from "./client";

export const punchActionSchema = z.enum(["clock_in", "break_start", "break_end", "clock_out"]);
export type PunchAction = z.infer<typeof punchActionSchema>;
export const punchStateSchema = z.object({
  state: z.enum(["not_clocked_in", "clocked_in", "on_break"]),
  last_action: punchActionSchema.nullable(),
  occurred_at: z.string().nullable(),
  server_observed_at: z.string(),
  elapsed_seconds: z.number().int().nonnegative().nullable(),
});
export type PunchState = z.infer<typeof punchStateSchema>;
export const timeEntrySchema = z.object({
  entry_id: z.string(), revision_id: z.string(), revision_number: z.number().int(),
  work_date: z.string(), timezone: z.string(),
  provenance: z.enum(["employee_punch", "authorized_manual_entry"]),
  start_at: z.string().nullable(), end_at: z.string().nullable(),
  approved_duration_minutes: z.number().int().nonnegative().nullable(),
  state: z.enum(["recorded", "submitted", "approved", "corrected"]),
  supersedes_revision_id: z.string().nullable(), correction_reason: z.string().nullable(), approved_at: z.string().nullable(),
});
export type TimeEntry = z.infer<typeof timeEntrySchema>;
export const jobClockActionSchema = z.enum(["start", "stop"]);
export type JobClockAction = z.infer<typeof jobClockActionSchema>;
export const jobWorkedIntervalSchema = z.object({
  interval_id: z.string(), revision_id: z.string(), revision_number: z.number().int().positive(),
  employee_id: z.string(), job_id: z.string(), appointment_id: z.string().nullable(),
  start_at: z.string(), stop_at: z.string(), duration_seconds: z.number().int().nonnegative(),
  source: z.enum(["employee_clock", "authorized_manual"]),
  correction_state: z.enum(["original", "corrected", "superseded"]),
  supersedes_revision_id: z.string().nullable(), audit_lineage: z.array(z.string()), source_event_ids: z.array(z.string()),
  validity: z.enum(["valid", "correction_required"]), confidence: z.enum(["authoritative", "disputed"]),
  evidence_digest: z.string(), correction_reason: z.string().nullable(),
});
export type JobWorkedInterval = z.infer<typeof jobWorkedIntervalSchema>;
export const activeJobClockSchema = z.object({
  active: z.boolean(), event_id: z.string().nullable(), employee_id: z.string(), job_id: z.string().nullable(),
  appointment_id: z.string().nullable(), started_at: z.string().nullable(), server_observed_at: z.string(),
  elapsed_seconds: z.number().int().nonnegative().nullable(),
});
export type ActiveJobClock = z.infer<typeof activeJobClockSchema>;
export const jobClockResultSchema = z.object({
  event_id: z.string(), action: jobClockActionSchema, occurred_at: z.string(), state: activeJobClockSchema,
  completed_interval: jobWorkedIntervalSchema.nullable(),
});
export type JobClockResult = z.infer<typeof jobClockResultSchema>;
const payPeriodSchema = z.object({ id: z.string(), period_start: z.string(), period_end: z.string(), processing_date: z.string(), payday: z.string(), timezone: z.string(), schedule_definition_id: z.string(), schedule_version: z.number().int() });
export const timecardSchema = z.object({ employee_id: z.string(), punch_state: punchStateSchema, pay_period: payPeriodSchema.nullable(), entries: z.array(timeEntrySchema), job_intervals: z.array(jobWorkedIntervalSchema).default([]) });
export type Timecard = z.infer<typeof timecardSchema>;
export const punchResultSchema = z.object({ punch_id: z.string(), action: punchActionSchema, occurred_at: z.string(), state: punchStateSchema, completed_entry: timeEntrySchema.nullable() });

export interface TimekeepingService {
  state(): Promise<PunchState>;
  timecard(): Promise<Timecard>;
  punch(action: PunchAction, idempotencyKey: string): Promise<z.infer<typeof punchResultSchema>>;
  jobClockState(): Promise<ActiveJobClock>;
  jobClock(action: JobClockAction, jobId: string, appointmentId: string | null, idempotencyKey: string): Promise<JobClockResult>;
}

export function createTimekeepingService(client: ApiClient): TimekeepingService {
  return {
    state: () => client.request("/api/v1/timekeeping/me/state", punchStateSchema),
    timecard: () => client.request("/api/v1/timekeeping/me/timecard", timecardSchema),
    punch: (action, idempotencyKey) => client.request("/api/v1/timekeeping/me/punches", punchResultSchema, { method: "POST", headers: { "Idempotency-Key": idempotencyKey }, body: JSON.stringify({ action }) }),
    jobClockState: () => client.request("/api/v1/timekeeping/me/job-clock", activeJobClockSchema),
    jobClock: (action, jobId, appointmentId, idempotencyKey) => client.request("/api/v1/timekeeping/me/job-clock", jobClockResultSchema, { method: "POST", headers: { "Idempotency-Key": idempotencyKey }, body: JSON.stringify({ action, job_id: jobId, appointment_id: appointmentId }) }),
  };
}
