import type { CustomerDisposition, FieldJobState, FieldNoteType } from "../types/technicianField";
import { apiClient } from "./client";

const ROOT = "/api/v1/technician";

export async function getFieldJob(jobId: string): Promise<FieldJobState> {
  return (await apiClient.get<FieldJobState>(`${ROOT}/jobs/${jobId}`)).data;
}

export async function addWorkNote(jobId: string, noteType: FieldNoteType, content: string, jobVersion: number, assignmentVersion: number): Promise<FieldJobState> {
  return (await apiClient.post<FieldJobState>(`${ROOT}/jobs/${jobId}/notes`, {
    note_type: noteType,
    content,
    idempotency_key: crypto.randomUUID(),
    expected_job_version: jobVersion,
    expected_assignment_version: assignmentVersion,
  })).data;
}

export async function recordCustomerDisposition(
  jobId: string,
  disposition: CustomerDisposition,
  customerName: string,
  reason: string,
  jobVersion: number,
  assignmentVersion: number,
): Promise<FieldJobState> {
  return (await apiClient.post<FieldJobState>(`${ROOT}/jobs/${jobId}/customer-approval`, {
    disposition,
    customer_name: disposition === "approved" ? customerName : null,
    reason: disposition === "approved" ? null : reason,
    idempotency_key: crypto.randomUUID(),
    expected_job_version: jobVersion,
    expected_assignment_version: assignmentVersion,
  })).data;
}

export async function refreshInvoiceHandoff(jobId: string, jobVersion: number, assignmentVersion: number): Promise<FieldJobState> {
  return (await apiClient.post<FieldJobState>(`${ROOT}/jobs/${jobId}/invoice-handoff`, {
    idempotency_key: crypto.randomUUID(),
    expected_job_version: jobVersion,
    expected_assignment_version: assignmentVersion,
  })).data;
}

export async function recordArrival(appointmentId: string, state: "en_route" | "arrived", expectedVersion: number) {
  return (await apiClient.post(`${"/api/v1/dispatch"}/appointments/${appointmentId}/assignment/arrival`, {
    state,
    expected_version: expectedVersion,
    idempotency_key: crypto.randomUUID(),
  })).data;
}

export async function transitionJob(jobId: string, action: "start" | "pause" | "resume" | "complete", expectedVersion: number) {
  return (await apiClient.post(`${"/api/v1/jobs"}/${jobId}/${action}`, {
    expected_version: expectedVersion,
    ...(action === "pause" ? { reason_code: "operational_hold" } : {}),
  })).data;
}
