import { describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import { getOwnPunchState, getOwnTimecard, recordOwnPunch } from "./timekeeping";

describe("Workday Time API client", () => {
  it("uses self-scoped endpoints and sends only an action with a fresh idempotency key", async () => {
    const keys: string[] = [];
    const adapter = vi.fn(async (config) => {
      keys.push(String(config.headers.get("Idempotency-Key")));
      expect(config.url).toBe("/api/v1/timekeeping/me/punches");
      expect(JSON.parse(String(config.data))).toEqual({ action: "clock_in" });
      expect(String(config.data)).not.toMatch(/employee|company|branch|timestamp|duration/i);
      return {
        data: { punch_id: "punch", action: "clock_in", occurred_at: "2026-08-28T12:00:00Z", state: {}, completed_entry: null },
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      };
    });
    const original = apiClient.defaults.adapter;
    apiClient.defaults.adapter = adapter;
    try {
      await recordOwnPunch("clock_in");
      await recordOwnPunch("clock_in");
    } finally {
      apiClient.defaults.adapter = original;
    }
    expect(keys[0]).toBeTruthy();
    expect(keys[1]).toBeTruthy();
    expect(keys[0]).not.toBe(keys[1]);
  });

  it("reads only the authenticated employee state and timecard endpoints", async () => {
    const adapter = vi.fn(async (config) => ({
      data: config.url?.endsWith("state")
        ? { state: "not_clocked_in", last_action: null, occurred_at: null, server_observed_at: "2026-08-28T12:00:00Z", elapsed_seconds: null }
        : { employee_id: "employee", punch_state: {}, pay_period: null, entries: [] },
      status: 200,
      statusText: "OK",
      headers: {},
      config,
    }));
    const original = apiClient.defaults.adapter;
    apiClient.defaults.adapter = adapter;
    try {
      await getOwnPunchState();
      await getOwnTimecard();
    } finally {
      apiClient.defaults.adapter = original;
    }
    expect(adapter.mock.calls.map(([config]) => config.url)).toEqual([
      "/api/v1/timekeeping/me/state",
      "/api/v1/timekeeping/me/timecard",
    ]);
  });
});
