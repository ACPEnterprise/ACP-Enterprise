import { apiClient } from "./client";
import type { JobCancellationReason, JobCreateFromAppointmentInput, JobCreateInput, JobDetail, JobListParams, JobMutationResponse, JobPauseReason, JobReopeningReason, JobVersionInput, PaginatedJobs } from "../types/jobs";

const JOBS_PATH = "/api/v1/jobs";

export async function listJobs(query: JobListParams): Promise<PaginatedJobs> {
  const response = await apiClient.get<PaginatedJobs>(JOBS_PATH, { params: {
    search_text: query.searchText || undefined, status: query.status, priority: query.priority,
    job_type: query.jobType, branch_id: query.branchId, page: query.page, page_size: query.pageSize,
    sort_field: query.sortField, sort_direction: query.sortDirection,
    appointment_id: query.appointmentId,
    customer_id: query.customerId,
  } });
  return response.data;
}
export async function getJob(jobId: string): Promise<JobDetail> { return (await apiClient.get<JobDetail>(`${JOBS_PATH}/${jobId}`)).data; }
export async function createJob(input: JobCreateInput): Promise<JobMutationResponse> { return (await apiClient.post<JobMutationResponse>(JOBS_PATH, input)).data; }
export async function createJobFromAppointment(input: JobCreateFromAppointmentInput): Promise<JobMutationResponse> { return (await apiClient.post<JobMutationResponse>(`${JOBS_PATH}/from-appointment`, input)).data; }
type LifecycleInput = JobVersionInput & { reason_code?: JobPauseReason | JobCancellationReason | JobReopeningReason };
async function lifecycle(jobId: string, action: string, input: LifecycleInput): Promise<JobMutationResponse> { return (await apiClient.post<JobMutationResponse>(`${JOBS_PATH}/${jobId}/${action}`, input)).data; }
export const activateJob = (jobId: string, input: JobVersionInput) => lifecycle(jobId, "activate", input);
export const startJob = (jobId: string, input: JobVersionInput) => lifecycle(jobId, "start", input);
export const pauseJob = (jobId: string, input: JobVersionInput & { reason_code: JobPauseReason }) => lifecycle(jobId, "pause", input);
export const resumeJob = (jobId: string, input: JobVersionInput) => lifecycle(jobId, "resume", input);
export const completeJob = (jobId: string, input: JobVersionInput) => lifecycle(jobId, "complete", input);
export const cancelJob = (jobId: string, input: JobVersionInput & { reason_code: JobCancellationReason }) => lifecycle(jobId, "cancel", input);
export const reopenJob = (jobId: string, input: JobVersionInput & { reason_code: JobReopeningReason }) => lifecycle(jobId, "reopen", input);
