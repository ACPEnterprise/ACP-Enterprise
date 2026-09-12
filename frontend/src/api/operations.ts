import { apiClient } from "./client";
import type {
  ServiceRequestCreateInput,
  ServiceRequestResult,
  ExistingJobScheduleInput,
  ExistingJobScheduleResult,
} from "../types/operations";

export async function createServiceRequest(
  input: ServiceRequestCreateInput,
): Promise<ServiceRequestResult> {
  return (
    await apiClient.post<ServiceRequestResult>(
      "/api/v1/operations/service-requests",
      input,
    )
  ).data;
}

export async function scheduleExistingJob(
  jobId: string,
  input: Omit<ExistingJobScheduleInput, "employee_id">,
): Promise<ExistingJobScheduleResult> {
  return (
    await apiClient.post<ExistingJobScheduleResult>(
      `/api/v1/operations/jobs/${jobId}/schedule`,
      input,
    )
  ).data;
}
