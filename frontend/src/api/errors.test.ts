import {
  AxiosError,
  AxiosHeaders,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from "axios";
import { describe, expect, it } from "vitest";

import { getOperatorApiError } from "./errors";

function failure(status?: number, detail?: unknown): AxiosError {
  const config = { headers: new AxiosHeaders() } as InternalAxiosRequestConfig;
  const response =
    status === undefined
      ? undefined
      : ({
          status,
          statusText: "failure",
          headers: new AxiosHeaders(),
          config,
          data: { detail },
        } satisfies AxiosResponse);
  return new AxiosError(
    "request failed",
    undefined,
    config,
    undefined,
    response,
  );
}

describe("operator API errors", () => {
  it.each([
    [failure(), "Service unreachable"],
    [failure(401), "Authentication required"],
    [
      failure(400, "Untrusted forwarding headers."),
      "Preview configuration error",
    ],
    [
      failure(409, {
        code: "engineering_execution_not_connected",
        message: "Worker offline.",
      }),
      "Worker unavailable",
    ],
    [
      failure(409, {
        code: "engineering_capacity_unavailable",
        message: "Busy.",
      }),
      "Engineering is at capacity",
    ],
    [
      failure(409, {
        code: "engineering_dependency_blocked",
        message: "Dependency incomplete.",
      }),
      "Prerequisite incomplete",
    ],
    [
      failure(422, {
        code: "engineering_command_invalid",
        message: "Policy rejected.",
      }),
      "Milestone cannot start",
    ],
    [failure(422, [{ msg: "Malformed milestone." }]), "Invalid milestone data"],
  ])("distinguishes owner-action failures", (error, title) => {
    expect(getOperatorApiError(error, "Milestone").title).toBe(title);
  });

  it.each([400, 409, 422])("does not reflect unstructured detail for status %s", (status) => {
    const result = getOperatorApiError(
      failure(status, "sql://provider-secret-customer-canary"),
      "Customer",
    );
    expect(result.message).not.toContain("provider-secret-customer-canary");
    expect(result.message).not.toContain("sql://");
  });
});
