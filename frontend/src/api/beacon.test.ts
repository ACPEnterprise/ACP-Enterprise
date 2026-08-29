import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  getBeaconLifecycleHistory,
  recordBeaconLifecycleAction,
} from "./beacon";
import { apiClient } from "./client";

vi.mock("./client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(apiClient.get).mockResolvedValue({ data: { items: [] } });
  vi.mocked(apiClient.post).mockResolvedValue({ data: { id: "event-id" } });
});

describe("Beacon lifecycle API", () => {
  it("submits exact evidence and explicit lifecycle operations", async () => {
    const signal = { id: "signal-id", evidence_digest: "a".repeat(64) };
    await recordBeaconLifecycleAction(signal, "acknowledge");
    expect(apiClient.post).toHaveBeenLastCalledWith(
      "/api/v1/beacon/signals/signal-id/acknowledge",
      {
        evidence_digest: signal.evidence_digest,
        request_id: expect.any(String),
      },
    );

    await recordBeaconLifecycleAction(
      signal,
      "snooze",
      "2026-07-29T18:00:00Z",
    );
    expect(apiClient.post).toHaveBeenLastCalledWith(
      "/api/v1/beacon/signals/signal-id/snooze",
      {
        evidence_digest: signal.evidence_digest,
        snooze_until: "2026-07-29T18:00:00Z",
      },
    );
  });

  it("loads Company-scoped history through the authenticated client", async () => {
    await getBeaconLifecycleHistory("condition-id");
    expect(apiClient.get).toHaveBeenCalledWith(
      "/api/v1/beacon/lifecycle-events",
      { params: { condition_key: "condition-id" } },
    );
  });
});
