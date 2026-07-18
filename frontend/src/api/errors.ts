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
