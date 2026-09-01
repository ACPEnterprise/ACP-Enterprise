import * as Crypto from "expo-crypto";
import { z } from "zod";
import type { ApiClient } from "./client";

const itineraryItemSchema = z.object({ appointment_id: z.string().uuid(), appointment_number: z.string(), job_id: z.string().uuid().nullable(), job_number: z.string().nullable(), job_status: z.string().nullable(), job_version: z.number().int().positive().nullable(), customer_display_name: z.string(), service_location_label: z.string(), window_start_at: z.string(), window_end_at: z.string(), assignment_status: z.string(), assignment_version: z.number().int().positive(), arrival_state: z.enum(["pending", "en_route", "arrived"]), field_execution_enabled: z.boolean() });
const itinerarySchema = z.object({ service_date: z.string(), technician_display_name: z.string(), items: z.array(itineraryItemSchema) });
export const fieldJobStateSchema = z.object({ job_id: z.string().uuid(), assignment_id: z.string().uuid(), work_summary_recorded: z.boolean(), customer_disposition: z.string().nullable(), completion_ready: z.boolean(), requirement_snapshot_version: z.number().int().positive().nullable(), missing_requirements: z.array(z.string()), commercial_authorization: z.enum(["accepted_estimate", "non_billable", "missing"]), non_billable_reason: z.string().nullable(), invoice_handoff_status: z.string().nullable(), invoice_id: z.string().uuid().nullable() });
export type ItineraryItem = z.infer<typeof itineraryItemSchema>; export type FieldJobState = z.infer<typeof fieldJobStateSchema>;
export interface FieldService {
  itinerary(serviceDate: string): Promise<z.infer<typeof itinerarySchema>>; state(jobId: string): Promise<FieldJobState>;
  arrival(appointmentId: string, state: "en_route" | "arrived", expectedVersion: number): Promise<void>;
  note(jobId: string, content: string, jobVersion: number, assignmentVersion: number): Promise<FieldJobState>;
  approval(jobId: string, disposition: "approved" | "unavailable" | "refused", jobVersion: number, assignmentVersion: number): Promise<FieldJobState>;
  refreshHandoff(jobId: string, jobVersion: number, assignmentVersion: number): Promise<FieldJobState>;
}
const key = (operation: string) => `mobile:${operation}:${Crypto.randomUUID()}`;
export function createFieldService(client: ApiClient): FieldService {
  return {
    itinerary: (date) => client.request(`/api/v1/technician/itinerary?service_date=${encodeURIComponent(date)}`, itinerarySchema),
    state: (job) => client.request(`/api/v1/technician/jobs/${encodeURIComponent(job)}`, fieldJobStateSchema),
    arrival: async (appointment, state, version) => { await client.request(`/api/v1/dispatch/appointments/${encodeURIComponent(appointment)}/assignment/arrival`, z.object({}).passthrough(), { method: "POST", body: JSON.stringify({ state, expected_version: version, idempotency_key: key(`arrival-${state}`) }) }); },
    note: (job, content, jobVersion, assignmentVersion) => client.request(`/api/v1/technician/jobs/${encodeURIComponent(job)}/notes`, fieldJobStateSchema, { method: "POST", body: JSON.stringify({ note_type: "work_performed", content, expected_job_version: jobVersion, expected_assignment_version: assignmentVersion, idempotency_key: key("work-summary") }) }),
    approval: (job, disposition, jobVersion, assignmentVersion) => client.request(`/api/v1/technician/jobs/${encodeURIComponent(job)}/customer-approval`, fieldJobStateSchema, { method: "POST", body: JSON.stringify({ disposition, customer_name: null, reason: null, expected_job_version: jobVersion, expected_assignment_version: assignmentVersion, idempotency_key: key(`approval-${disposition}`) }) }),
    refreshHandoff: (job, jobVersion, assignmentVersion) => client.request(`/api/v1/technician/jobs/${encodeURIComponent(job)}/invoice-handoff`, fieldJobStateSchema, { method: "POST", body: JSON.stringify({ expected_job_version: jobVersion, expected_assignment_version: assignmentVersion, idempotency_key: key("invoice-handoff") }) }),
  };
}
