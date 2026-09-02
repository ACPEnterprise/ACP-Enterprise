import { z } from "zod";
import * as Crypto from "expo-crypto";
import type { ApiClient } from "./client";

const itineraryItemSchema = z.object({
  appointment_id: z.string().uuid(), appointment_number: z.string(), job_id: z.string().uuid().nullable(),
  job_number: z.string().nullable(), job_status: z.string().nullable(), job_version: z.number().int().positive().nullable(),
  customer_display_name: z.string(), service_location_label: z.string(), window_start_at: z.string().datetime({ offset: true }),
  window_end_at: z.string().datetime({ offset: true }), assignment_status: z.string(), assignment_version: z.number().int().positive(),
  arrival_state: z.string(), field_execution_enabled: z.boolean(),
}).strict();
const itinerarySchema = z.object({ service_date: z.string().date(), technician_display_name: z.string(), items: z.array(itineraryItemSchema) }).strict();
const fieldJobStateSchema = z.object({
  job_id: z.string().uuid(), assignment_id: z.string().uuid(), work_summary_recorded: z.boolean(), customer_disposition: z.string().nullable(),
  completion_ready: z.boolean(), requirement_snapshot_version: z.number().int().positive().nullable(), missing_requirements: z.array(z.string()),
  commercial_authorization: z.enum(["accepted_estimate", "non_billable", "missing"]), non_billable_reason: z.string().nullable(),
  invoice_handoff_status: z.string().nullable(), invoice_id: z.string().uuid().nullable(),
}).strict();
const jobMutationSchema = z.object({ id: z.string().uuid(), status: z.string(), concurrency_version: z.number().int().positive() }).passthrough();
const assignmentSchema = z.object({ version: z.number().int().positive(), arrival_state: z.string(), status: z.string() }).passthrough();

export type ItineraryItem = z.infer<typeof itineraryItemSchema>;
export type Itinerary = z.infer<typeof itinerarySchema>;
export type FieldJobState = z.infer<typeof fieldJobStateSchema>;
export type JobAction = "start" | "pause" | "resume" | "complete";

export interface FieldService {
  itinerary(date: string): Promise<Itinerary>;
  state(jobId: string): Promise<FieldJobState>;
  arrival(appointmentId: string, state: "en_route" | "arrived", expectedVersion: number, key: string): Promise<{ version: number; arrival_state: string; status: string }>;
  transition(jobId: string, action: JobAction, expectedVersion: number): Promise<{ id: string; status: string; concurrency_version: number }>;
  workSummary(jobId: string, content: string, jobVersion: number, assignmentVersion: number, key: string): Promise<FieldJobState>;
  customerDisposition(jobId: string, disposition: "approved" | "unavailable" | "refused", customerName: string | null, reason: string | null, jobVersion: number, assignmentVersion: number, key: string): Promise<FieldJobState>;
}

export function fieldIdempotencyKey(action: string) { return `mobile-field:${action}:${Crypto.randomUUID()}`; }

export function createFieldService(client: ApiClient): FieldService {
  return {
    itinerary: (date) => client.request(`/api/v1/technician/itinerary?service_date=${encodeURIComponent(date)}`, itinerarySchema),
    state: (jobId) => client.request(`/api/v1/technician/jobs/${encodeURIComponent(jobId)}`, fieldJobStateSchema),
    arrival: (appointmentId, state, expectedVersion, key) => client.request(`/api/v1/dispatch/appointments/${encodeURIComponent(appointmentId)}/assignment/arrival`, assignmentSchema, { method: "POST", body: JSON.stringify({ state, expected_version: expectedVersion, idempotency_key: key }) }),
    transition: (jobId, action, expectedVersion) => client.request(`/api/v1/jobs/${encodeURIComponent(jobId)}/${action}`, jobMutationSchema, { method: "POST", body: JSON.stringify(action === "pause" ? { expected_version: expectedVersion, reason_code: "operational_hold" } : { expected_version: expectedVersion }) }),
    workSummary: (jobId, content, jobVersion, assignmentVersion, key) => client.request(`/api/v1/technician/jobs/${encodeURIComponent(jobId)}/notes`, fieldJobStateSchema, { method: "POST", body: JSON.stringify({ note_type: "work_performed", content, idempotency_key: key, expected_job_version: jobVersion, expected_assignment_version: assignmentVersion }) }),
    customerDisposition: (jobId, disposition, customerName, reason, jobVersion, assignmentVersion, key) => client.request(`/api/v1/technician/jobs/${encodeURIComponent(jobId)}/customer-approval`, fieldJobStateSchema, { method: "POST", body: JSON.stringify({ disposition, customer_name: customerName, reason, idempotency_key: key, expected_job_version: jobVersion, expected_assignment_version: assignmentVersion }) }),
  };
}
