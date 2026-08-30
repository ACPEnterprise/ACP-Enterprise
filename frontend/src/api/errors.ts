import axios from "axios";

export function getApiErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (Array.isArray(detail)) {
      return detail.map((item) => item.msg ?? "Invalid value").join(" ");
    }
    return error.message;
  }
  return error instanceof Error
    ? error.message
    : "An unexpected error occurred.";
}

export function getOperatorApiError(
  error: unknown,
  resource = "Job",
): { title: string; message: string; retryable: boolean } {
  if (!axios.isAxiosError(error))
    return {
      title: "Unexpected error",
      message: "The operation could not be completed.",
      retryable: false,
    };
  const status = error.response?.status;
  const detail = error.response?.data?.detail;
  const code =
    typeof detail === "object" && detail !== null && "code" in detail
      ? String(detail.code)
      : null;
  const structuredMessage =
    typeof detail === "object" && detail !== null && "message" in detail
      ? String(detail.message)
      : null;
  if (!error.response)
    return {
      title: "Service unreachable",
      message: `The ${resource} service could not be reached. Check your connection and try again.`,
      retryable: true,
    };
  if (status === 401)
    return {
      title: "Authentication required",
      message: "Your session is no longer valid. Sign in again.",
      retryable: false,
    };
  if (status === 403)
    return {
      title: "Access denied",
      message: `You do not have permission to perform this ${resource} operation.`,
      retryable: false,
    };
  if (status === 404)
    return {
      title: `${resource} not found`,
      message: `The ${resource} is unavailable or outside your accessible Branches.`,
      retryable: false,
    };
  if (status === 400 && detail === "Untrusted forwarding headers.")
    return {
      title: "Preview configuration error",
      message:
        "Mission Control rejected the Preview proxy configuration. The service operator must restore the trusted route.",
      retryable: false,
    };
  if (status === 400)
    return {
      title: "Request rejected",
      message: structuredMessage ?? "Review the request and correct the entered information.",
      retryable: false,
    };
  if (status === 409 && code === "engineering_execution_not_connected")
    return {
      title: "Worker unavailable",
      message:
        structuredMessage ?? "The authenticated worker is not connected.",
      retryable: false,
    };
  if (status === 409 && code === "engineering_capacity_unavailable")
    return {
      title: "Engineering is at capacity",
      message:
        structuredMessage ??
        "Wait for current work to finish before starting another milestone.",
      retryable: false,
    };
  if (status === 409 && code === "engineering_dependency_blocked")
    return {
      title: "Prerequisite incomplete",
      message:
        structuredMessage ??
        "Complete the required earlier milestone before starting this work.",
      retryable: false,
    };
  if (status === 409)
    return {
      title: `${resource} changed`,
      message: structuredMessage ?? "Refresh the authoritative record before trying again.",
      retryable: false,
    };
  if (status === 422 && code === "engineering_command_invalid")
    return {
      title: "Milestone cannot start",
      message:
        structuredMessage ??
        "Repository policy rejected this milestone definition.",
      retryable: false,
    };
  if (status === 422)
    return {
      title: "Invalid milestone data",
      message: structuredMessage ?? "Review the entered information and correct invalid values.",
      retryable: false,
    };
  return {
    title: "Service unavailable",
    message: "The service could not be reached. Try again.",
    retryable: true,
  };
}

export function shouldRetryApiQuery(
  failureCount: number,
  error: unknown,
): boolean {
  return failureCount < 2 && getOperatorApiError(error).retryable;
}
