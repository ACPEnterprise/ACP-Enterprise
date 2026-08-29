import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  getBeaconSignals,
  getBeaconLifecycleHistory,
  getBeaconWorkflowHistory,
  recordBeaconLifecycleAction,
  recordBeaconWorkflowAction,
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
  it("uses the accepted operational workflow projection for the active queue", async () => {
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({
        data: {
          items: [],
          snoozed_items: [],
          lifecycle_commands_available: true,
        },
      })
      .mockResolvedValueOnce({
        data: {
          ranking_version: "BANK.BEA.004.v1",
          ranking_digest: "ranking-digest",
          items: [],
        },
      });
    await getBeaconSignals();
    expect(apiClient.get).toHaveBeenNthCalledWith(
      2,
      "/api/v1/beacon/operational-signals/workflow",
      { params: { view: "all" } },
    );
  });

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

  it("binds ownership commands to evidence and optimistic version", async () => {
    const signal = { id: "signal-id", evidence_digest: "a".repeat(64) };
    await recordBeaconWorkflowAction(signal, "transfer", 4, "user-b");
    expect(apiClient.post).toHaveBeenCalledWith(
      "/api/v1/beacon/signals/signal-id/transfer",
      {
        evidence_digest: signal.evidence_digest,
        request_id: expect.any(String),
        expected_version: 4,
        owner_user_id: "user-b",
      },
    );
    await getBeaconWorkflowHistory("condition-id");
    expect(apiClient.get).toHaveBeenLastCalledWith(
      "/api/v1/beacon/workflow-history",
      { params: { condition_key: "condition-id" } },
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
