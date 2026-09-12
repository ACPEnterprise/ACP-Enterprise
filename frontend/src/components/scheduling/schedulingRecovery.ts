import axios from "axios";

import { getOperatorApiError } from "../../api/errors";

export type SchedulingRecoveryState =
  | "FAILED"
  | "FAILED_REQUIRES_REFRESH"
  | "UNKNOWN_REQUIRES_REFRESH";

export interface SchedulingRecovery {
  readonly state: SchedulingRecoveryState;
  readonly title: string;
  readonly message: string;
  readonly retryLabel: string | null;
}

const detailValue = (error: unknown, key: "code" | "recovery") => {
  if (!axios.isAxiosError(error)) return null;
  const detail = error.response?.data?.detail;
  return typeof detail === "object" && detail !== null && key in detail
    ? String(detail[key])
    : null;
};

export function schedulingMutationRecovery(
  error: unknown,
  resource: "booking" | "Job scheduling" | "appointment move",
): SchedulingRecovery {
  const safe = getOperatorApiError(error, resource);
  const code = detailValue(error, "code");
  const recovery = detailValue(error, "recovery");
  const noResponse = axios.isAxiosError(error) && !error.response;
  const serverFailure = axios.isAxiosError(error) && (error.response?.status ?? 0) >= 500;
  const uncertain = noResponse || serverFailure || recovery === "RECONCILIATION_REQUIRED" || code === "reconciliation_required" || code === "provider_uncertain";

  if (uncertain) {
    return {
      state: "UNKNOWN_REQUIRES_REFRESH",
      title: "Outcome requires review",
      message: "ACP could not confirm whether the operation finished. Authoritative Job, Appointment, and Dispatch state was refreshed. Review it before retrying the same request.",
      retryLabel: "Retry same request",
    };
  }
  if (code === "stale_version") {
    return {
      state: "FAILED_REQUIRES_REFRESH",
      title: "Record changed",
      message: "The record changed after it was loaded. ACP refreshed authoritative state; review the current Job or Appointment before trying again.",
      retryLabel: null,
    };
  }
  if (code === "concurrency_conflict") {
    return {
      state: "FAILED_REQUIRES_REFRESH",
      title: "Scheduling conflict",
      message: "The requested technician, time, or capacity now conflicts with authoritative Scheduling state. Review the refreshed schedule before choosing another option.",
      retryLabel: null,
    };
  }
  if (code === "resource_state_conflict") {
    return {
      state: "FAILED_REQUIRES_REFRESH",
      title: "Work changed",
      message: "The Job or Appointment is no longer in the state shown when this action began. Review the refreshed record before continuing.",
      retryLabel: null,
    };
  }
  if (code === "idempotency_conflict") {
    return {
      state: "FAILED_REQUIRES_REFRESH",
      title: "Request no longer matches",
      message: "This request identity was already used for different booking details. Nothing was retried. Review authoritative state and submit the corrected intent as a new request.",
      retryLabel: null,
    };
  }
  if (recovery === "USER_CORRECTION_REQUIRED" || code === "validation") {
    return {
      state: "FAILED",
      title: "Booking details rejected",
      message: "No booking was accepted. Correct the Branch, arrival window, duration, Customer, Location, or other highlighted details before submitting again.",
      retryLabel: null,
    };
  }
  return {
    state: "FAILED",
    title: safe.title,
    message: safe.message,
    retryLabel: safe.retryable ? "Retry same request" : null,
  };
}
