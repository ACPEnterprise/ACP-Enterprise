import { describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import { correctTimeEntry, getAdminTimecardReview, getOwnActiveJobClock, getOwnPunchState, getOwnTimecard, recordOwnJobClock, recordOwnPunch } from "./timekeeping";

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

  it("uses the permission-gated administration review endpoint", async () => {
    const adapter = vi.fn(async (config) => ({
      data: { pay_period: null, items: [] },
      status: 200,
      statusText: "OK",
      headers: {},
      config,
    }));
    const original = apiClient.defaults.adapter;
    apiClient.defaults.adapter = adapter;
    try {
      await getAdminTimecardReview();
    } finally {
      apiClient.defaults.adapter = original;
    }
    expect(adapter.mock.calls[0]?.[0].url).toBe(
      "/api/v1/timekeeping/admin/timecard-review",
    );
  });

  it("keeps Job clock identity server-owned and reuses the caller retry key", async () => {
    const adapter = vi.fn(async (config) => {
      expect(config.url).toBe("/api/v1/timekeeping/me/job-clock");
      expect(config.headers.get("Idempotency-Key")).toBe("phone-persisted-key");
      expect(JSON.parse(String(config.data))).toEqual({
        action: "start",
        job_id: "job-1",
        appointment_id: "appointment-1",
      });
      expect(String(config.data)).not.toMatch(/employee|timestamp|duration/i);
      return { data: {}, status: 200, statusText: "OK", headers: {}, config };
    });
    const original = apiClient.defaults.adapter;
    apiClient.defaults.adapter = adapter;
    try {
      await recordOwnJobClock("start", "job-1", "appointment-1", "phone-persisted-key");
    } finally {
      apiClient.defaults.adapter = original;
    }
  });

  it("reads active Job clock state independently from paid punch state", async () => {
    const adapter = vi.fn(async (config) => ({
      data: { active: false, employee_id: "employee" },
      status: 200,
      statusText: "OK",
      headers: {},
      config,
    }));
    const original = apiClient.defaults.adapter;
    apiClient.defaults.adapter = adapter;
    try {
      await getOwnActiveJobClock();
    } finally {
      apiClient.defaults.adapter = original;
    }
    expect(adapter.mock.calls[0]?.[0].url).toBe("/api/v1/timekeeping/me/job-clock");
  });

  it("sends a classified correction with retry identity and no reviewer identity", async () => {
    const adapter = vi.fn(async (config) => {
      expect(config.url).toBe("/api/v1/timekeeping/entries/revision-1/corrections");
      expect(config.headers.get("Idempotency-Key")).toBeTruthy();
      expect(JSON.parse(String(config.data))).toEqual({
        correction_kind: "incorrect_stop",
        start_at: "2026-08-28T13:00:00Z",
        end_at: "2026-08-28T14:30:00Z",
        approved_duration_minutes: null,
        reason: "Verified against dispatch evidence",
      });
      expect(String(config.data)).not.toMatch(/reviewer|user_id/i);
      return { data: {}, status: 200, statusText: "OK", headers: {}, config };
    });
    const original = apiClient.defaults.adapter;
    apiClient.defaults.adapter = adapter;
    try {
      await correctTimeEntry("revision-1", {
        correction_kind: "incorrect_stop",
        start_at: "2026-08-28T13:00:00Z",
        end_at: "2026-08-28T14:30:00Z",
        approved_duration_minutes: null,
        reason: "Verified against dispatch evidence",
      });
    } finally {
      apiClient.defaults.adapter = original;
    }
  });
});
