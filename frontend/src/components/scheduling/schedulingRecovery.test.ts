import { AxiosError, AxiosHeaders, type AxiosResponse, type InternalAxiosRequestConfig } from "axios";
import { describe, expect, it } from "vitest";

import { schedulingMutationRecovery } from "./schedulingRecovery";

const failure = (status?: number, detail?: unknown) => {
  const config = { headers: new AxiosHeaders() } as InternalAxiosRequestConfig;
  const response = status ? ({ status, statusText: "failure", headers: new AxiosHeaders(), config, data: { detail } } satisfies AxiosResponse) : undefined;
  return new AxiosError("safe failure", undefined, config, undefined, response);
};

describe("Scheduling mutation recovery", () => {
  it("treats a timeout or lost response as unknown and requires authoritative review", () => {
    expect(schedulingMutationRecovery(failure(), "booking")).toMatchObject({
      state: "UNKNOWN_REQUIRES_REFRESH",
      title: "Outcome requires review",
      retryLabel: "Retry same request",
    });
    expect(schedulingMutationRecovery(failure(503), "booking").state).toBe("UNKNOWN_REQUIRES_REFRESH");
  });

  it.each([
    ["stale_version", "Record changed"],
    ["concurrency_conflict", "Scheduling conflict"],
    ["resource_state_conflict", "Work changed"],
    ["idempotency_conflict", "Request no longer matches"],
  ])("keeps %s distinct instead of flattening it", (code, title) => {
    expect(schedulingMutationRecovery(failure(409, { code, recovery: "RETRY_AFTER_REFRESH", message: "safe" }), "Job scheduling")).toMatchObject({
      state: "FAILED_REQUIRES_REFRESH",
      title,
    });
  });

  it("requires correction for authoritative validation rejection", () => {
    expect(schedulingMutationRecovery(failure(422, { code: "validation", recovery: "USER_CORRECTION_REQUIRED" }), "booking")).toMatchObject({
      state: "FAILED",
      title: "Booking details rejected",
      retryLabel: null,
    });
  });

  it("keeps authorization rejection definitive and non-retryable", () => {
    expect(schedulingMutationRecovery(failure(403, { code: "forbidden", recovery: "TERMINAL_FAILURE" }), "booking")).toMatchObject({
      state: "FAILED",
      title: "Access denied",
      retryLabel: null,
    });
  });
});
