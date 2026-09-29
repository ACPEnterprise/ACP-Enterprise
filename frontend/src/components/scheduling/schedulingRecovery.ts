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
  resource: "booking" | "Job scheduling" | "appointment move" | "Dispatch assignment",
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
  if (code === "scheduling_calendar_missing") {
    return {
      state: "FAILED",
      title: "Branch scheduling setup required",
      message: "This Branch has no approved capacity calendar. An authorized owner must establish Branch operating hours and capacity before assigned work can be booked.",
      retryLabel: null,
    };
  }
  if (code === "scheduling_calendar_unavailable") {
    return {
      state: "FAILED_REQUIRES_REFRESH",
      title: "Branch schedule unavailable",
      message: "The configured Branch capacity calendar could not be verified. No booking was accepted; refresh once and contact Enterprise Operations if it remains unavailable.",
      retryLabel: null,
    };
  }
  if (code === "scheduling_calendar_closed") {
    return {
      state: "FAILED",
      title: "Branch closed at requested time",
      message: "The requested arrival and work interval overlaps a configured Branch closure. Choose an open operating interval.",
      retryLabel: null,
    };
  }
  if (code === "scheduling_interval_unavailable") {
    return {
      state: "FAILED",
      title: "Outside Branch operating hours",
      message: "The requested technician work interval is outside configured Branch hours. Choose a time covered by the Branch calendar.",
      retryLabel: null,
    };
  }
  if (code === "scheduling_capacity_exhausted") {
    return {
      state: "FAILED",
      title: "Branch capacity already committed",
      message: "The requested technician work interval has no remaining Branch capacity. Review existing work for that interval or choose another planned start.",
      retryLabel: null,
    };
  }
  const policyValidation = {
    scheduling_invalid_timezone: [
      "Branch timezone requires correction",
      "The Branch scheduling timezone is invalid. An authorized administrator must correct Branch Scheduling Setup before booking.",
    ],
    scheduling_minimum_notice: [
      "Inside minimum-notice window",
      "The planned start is too soon for the configured Branch minimum notice. Choose a start after that boundary.",
    ],
    scheduling_booking_horizon: [
      "Beyond booking horizon",
      "The planned start is beyond the configured Branch booking horizon. Choose a date within the allowed horizon.",
    ],
    scheduling_cross_day: [
      "Work interval crosses the Branch day",
      "The arrival window or expected duration crosses into another Branch calendar day. Keep this visit within one operating day.",
    ],
    scheduling_slot_alignment: [
      "Start time does not match booking intervals",
      "The planned start must align with the Branch booking interval. Choose a start shown by the configured schedule.",
    ],
    scheduling_invalid_window: [
      "Arrival window is invalid",
      "The arrival-window end must be after its start.",
    ],
  } as const;
  if (code && code in policyValidation) {
    const [title, message] = policyValidation[code as keyof typeof policyValidation];
    return { state: "FAILED", title, message, retryLabel: null };
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
