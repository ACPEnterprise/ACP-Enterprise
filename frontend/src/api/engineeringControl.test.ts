import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import {
  approveEngineeringCommand,
  cancelEngineeringCommand,
  getEngineeringCommand,
  listEngineeringCommands,
} from "./engineeringControl";

vi.mock("./client", () => ({ apiClient: { get: vi.fn(), post: vi.fn() } }));

beforeEach(() => vi.resetAllMocks());

describe("Engineering Control API", () => {
  it("centralizes list and detail endpoints", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { items: [] } });
    await listEngineeringCommands({ approvalState: "approved", page: 2, pageSize: 20 });
    expect(apiClient.get).toHaveBeenCalledWith("/api/v1/engineering-commands", {
      params: { approval_state: "approved", page: 2, page_size: 20 },
    });
    await getEngineeringCommand("command-1");
    expect(apiClient.get).toHaveBeenLastCalledWith("/api/v1/engineering-commands/command-1");
  });

  it("sends exact approval and controlled cancellation evidence", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { id: "command-1" } });
    const approval = {
      expected_version: 3,
      instruction_digest: "a".repeat(64),
      request_digest: "b".repeat(64),
      repository_key: "acp-enterprise",
      expected_branch: "customer-management-v1",
      expected_head: "c".repeat(40),
      requested_code_changes: true,
    };
    await approveEngineeringCommand("command-1", approval);
    expect(apiClient.post).toHaveBeenCalledWith(
      "/api/v1/engineering-commands/command-1/approve",
      approval,
    );
    await cancelEngineeringCommand("command-1", {
      expected_version: 3,
      reason_code: "scope_changed",
    });
    expect(apiClient.post).toHaveBeenLastCalledWith(
      "/api/v1/engineering-commands/command-1/cancel",
      { expected_version: 3, reason_code: "scope_changed" },
    );
  });
});
