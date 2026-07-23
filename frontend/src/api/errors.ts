import axios from "axios";

export function getApiErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (Array.isArray(detail)) {
      return detail
        .map((item) => item.msg ?? "Invalid value")
        .join(" ");
    }
    return error.message;
  }
  return error instanceof Error ? error.message : "An unexpected error occurred.";
}

export function getOperatorApiError(error: unknown, resource = "Job"): { title: string; message: string; retryable: boolean } {
  if (!axios.isAxiosError(error)) return { title: "Unexpected error", message: "The operation could not be completed.", retryable: false };
  const status = error.response?.status;
  if (status === 401) return { title: "Authentication required", message: "Your session is no longer valid. Sign in again.", retryable: false };
  if (status === 403) return { title: "Access denied", message: `You do not have permission to perform this ${resource} operation.`, retryable: false };
  if (status === 404) return { title: `${resource} not found`, message: `The ${resource} is unavailable or outside your accessible Branches.`, retryable: false };
  if (status === 409) return { title: `${resource} changed`, message: `The ${resource} state changed. Refresh it before trying again.`, retryable: false };
  if (status === 422) return { title: "Check the request", message: getApiErrorMessage(error), retryable: false };
  return { title: "Service unavailable", message: "The service could not be reached. Try again.", retryable: true };
}

export function shouldRetryApiQuery(failureCount: number, error: unknown): boolean {
  return failureCount < 2 && getOperatorApiError(error).retryable;
}
