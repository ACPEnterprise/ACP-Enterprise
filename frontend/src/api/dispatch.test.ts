import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import { reportDispatchException } from "./dispatch";

vi.mock("./client", () => ({
  apiClient: { post: vi.fn() },
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
});
