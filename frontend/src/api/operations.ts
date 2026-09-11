import { apiClient } from "./client";
import type {
  ServiceRequestCreateInput,
  ServiceRequestResult,
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
