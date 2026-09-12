import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import { assignPrimary, reportDispatchException } from "./dispatch";

vi.mock("./client", () => ({
  apiClient: { post: vi.fn(), put: vi.fn() },
}));

describe("Dispatch API", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("crypto", { randomUUID: () => "dispatch-idempotency-key" });
  });

  it("posts a controlled exception with version and retry evidence", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: { id: "assignment-1" },
    });

    await reportDispatchException(
      "appointment-1",
      4,
      "Unsafe access",
      "safety_condition",
    );

    expect(apiClient.post).toHaveBeenCalledWith(
      "/api/v1/dispatch/appointments/appointment-1/assignment/exceptions",
      {
        reason: "Unsafe access",
        exception_code: "safety_condition",
        idempotency_key: "dispatch-idempotency-key",
        expected_version: 4,
      },
    );
  });

  it("accepts a caller-owned idempotency identity for composite scheduling", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { id: "assignment-1" } });
    await assignPrimary(
      "appointment-1",
      "employee-1",
      "Office assignment",
      undefined,
      "schedule-assignment:request-1",
    );
    expect(apiClient.post).toHaveBeenCalledWith(
      "/api/v1/dispatch/appointments/appointment-1/assignment",
      expect.objectContaining({ idempotency_key: "schedule-assignment:request-1" }),
    );
  });
});
