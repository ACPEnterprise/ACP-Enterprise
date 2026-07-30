import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { apiClient } from "../../../api/client";
import { getExecutionStatus, executionStatusPath } from "./api";
import { ExecutionMonitoringPanel } from "./ExecutionMonitoringPanel";
import {
  DEFAULT_EXECUTION_POLLING_MS,
  executionPollingInterval,
  useExecutionStatus,
} from "./hooks";
import type { MobileExecutionStatus } from "./types";

vi.mock("../../../api/client", () => ({
  apiClient: { get: vi.fn() },
}));
vi.mock("./hooks", async (importOriginal) => {
  const original = await importOriginal<typeof import("./hooks")>();
  return { ...original, useExecutionStatus: vi.fn() };
});
vi.mock("../owner-workflow/EngineeringOwnerWorkflow", () => ({
  EngineeringOwnerWorkflow: () => <div>Owner workflow</div>,
}));

const status: MobileExecutionStatus = {
  command_id: "command-id",
  ecid: "ECID-2026-000001",
  approval_state: "approved",
  monitoring_state: "disconnected",
  execution_available: true,
  execution_connected: false,
  connection_state: "disconnected",
  transport_health: "unavailable",
  execution_id: "execution-id",
  execution_state: "execution_not_connected",
  execution_status: "disconnected",
  progress_label: "Execution not connected",
  requested_at: "2026-07-24T12:00:00Z",
  started_at: null,
  finished_at: null,
  updated_at: "2026-07-24T12:00:00Z",
  lease: {
    availability: "unavailable",
    worker_id: null,
    status: null,
    started_at: null,
    expires_at: null,
    released_at: null,
    phase: "inactive",
  },
  heartbeat: {
    availability: "unavailable",
    health: null,
    last_seen: null,
    age_seconds: null,
  },
  transport_session: {
    availability: "unavailable",
    state: null,
    established_at: null,
    expires_at: null,
    last_contact_at: null,
  },
  result: {
    availability: "unavailable",
    status: null,
    validation_available: false,
    evidence_available: false,
    output_reference_count: 0,
    failure_classification: "provider_not_connected",
    created_at: null,
  },
  review_available: false,
  review_id: null,
  review_state: null,
  review_version: null,
  review_decided_at: null,
  authorization_required: true,
  authorization_status: null,
  authorization_id: null,
  authorized_at: null,
  authorization_expires_at: null,
  authorization_revoked_at: null,
  authorization_consumed_at: null,
  authorized_operation_type: null,
  authorization_eligible: false,
  repository_operation_required: true,
  repository_operation_id: null,
  repository_operation_type: null,
  repository_operation_status: null,
  repository_operation_eligible: false,
  repository_operation_expected_branch: null,
  repository_operation_resulting_commit_sha: null,
  repository_operation_requested_at: null,
  repository_operation_reserved_at: null,
  repository_operation_started_at: null,
  repository_operation_completed_at: null,
  repository_operation_failed_at: null,
  repository_operation_reconciliation_at: null,
  repository_operation_failure_classification: null,
  repository_operation_owner_attention_required: false,
  timeline: [
    { event: "execution_requested", occurred_at: "2026-07-24T12:00:00Z" },
  ],
  terminal: false,
  polling_after_seconds: 30,
};

describe("mobile execution monitoring", () => {
  it("uses a centralized read-only endpoint", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: status });
    expect(await getExecutionStatus("command-id")).toEqual(status);
    expect(apiClient.get).toHaveBeenCalledWith(
      executionStatusPath("command-id"),
    );
  });

  it("bounds polling and stops for terminal states", () => {
    expect(executionPollingInterval(undefined)).toBe(
      DEFAULT_EXECUTION_POLLING_MS,
    );
    expect(
      executionPollingInterval({ ...status, polling_after_seconds: 1 }),
    ).toBe(10_000);
    expect(
      executionPollingInterval({ ...status, polling_after_seconds: 500 }),
    ).toBe(120_000);
    expect(
      executionPollingInterval({
        ...status,
        terminal: true,
        polling_after_seconds: null,
      }),
    ).toBe(false);
  });

  it("renders honest disconnected and unavailable states with manual refresh", async () => {
    const refetch = vi.fn();
    vi.mocked(useExecutionStatus).mockReturnValue({
      isLoading: false,
      isError: false,
      isFetching: false,
      data: status,
      refetch,
    } as never);
    render(<ExecutionMonitoringPanel commandId="command-id" />);

    expect(screen.getByText("Worker transport: Disconnected")).toBeInTheDocument();
    expect(
      screen.getByText(/No live progress is being inferred/i),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /execute|cancel/i })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(refetch).toHaveBeenCalledOnce();
  });

  it("renders connected transport evidence without claiming execution", () => {
    vi.mocked(useExecutionStatus).mockReturnValue({
      isLoading: false,
      isError: false,
      isFetching: false,
      data: {
        ...status,
        connection_state: "connected",
        transport_health: "healthy",
        heartbeat: {
          availability: "available",
          health: "healthy",
          last_seen: "2026-07-24T12:00:00Z",
          age_seconds: 8,
        },
        transport_session: {
          availability: "available",
          state: "active",
          established_at: "2026-07-24T11:59:00Z",
          expires_at: "2026-07-24T12:14:00Z",
          last_contact_at: "2026-07-24T12:00:00Z",
        },
      },
      refetch: vi.fn(),
    } as never);
    render(<ExecutionMonitoringPanel commandId="command-id" />);

    expect(screen.getByText("Worker transport: Connected")).toBeInTheDocument();
    expect(screen.getByText("8 seconds")).toBeInTheDocument();
    expect(
      screen.getByText(/does not mean engineering execution has started/i),
    ).toBeInTheDocument();
  });

  it("does not offer a retry for authentication failures", () => {
    vi.mocked(useExecutionStatus).mockReturnValue({
      isLoading: false,
      isError: true,
      error: {
        isAxiosError: true,
        response: { status: 401 },
        config: {},
        toJSON: () => ({}),
      },
    } as never);
    render(<ExecutionMonitoringPanel commandId="command-id" />);
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });
});
