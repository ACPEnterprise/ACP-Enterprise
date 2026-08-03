import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../../api/client";
import {
  approveMobileReview,
  cancelMobileReview,
  getMobileCommandStatus,
  getMobileReview,
  listMobileReviews,
  listMobileWorkstreams,
  MOBILE_ENGINEERING_PATH,
  MOBILE_OWNER_REVIEWS_PATH,
  MOBILE_WORKSTREAMS_PATH,
  ENGINEERING_CAPACITY_PATH,
  getCapacitySummary,
  updateCapacityPolicy,
} from "./api";

vi.mock("../../api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
  },
}));

beforeEach(() => vi.resetAllMocks());

describe("mobile Engineering API client", () => {
  it("centralizes pending review, detail, and status paths", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { items: [] } });
    await listMobileReviews({ page: 2, pageSize: 10 });
    expect(apiClient.get).toHaveBeenCalledWith(MOBILE_OWNER_REVIEWS_PATH, {
      params: { page: 2, page_size: 10 },
    });

    await listMobileWorkstreams({ page: 3, pageSize: 5 });
    expect(apiClient.get).toHaveBeenCalledWith(MOBILE_WORKSTREAMS_PATH, {
      params: { page: 3, page_size: 5 },
    });

    await getMobileReview("command-id");
    expect(apiClient.get).toHaveBeenCalledWith(
      `${MOBILE_ENGINEERING_PATH}/command-id`,
    );

    await getMobileCommandStatus("command-id");
    expect(apiClient.get).toHaveBeenCalledWith(
      "/api/v1/engineering/mobile/commands/command-id/status",
    );
  });

  it("sends bounded approval and cancellation payloads without retries", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { id: "command-id" } });
    const approval = {
      expected_version: 1,
      instruction_digest: "a".repeat(64),
      request_digest: "b".repeat(64),
      repository_key: "acp-enterprise",
      expected_branch: "customer-management-v1",
      expected_head: "c".repeat(40),
      requested_code_changes: true,
    };
    await approveMobileReview("command-id", approval);
    expect(apiClient.post).toHaveBeenCalledWith(
      `${MOBILE_ENGINEERING_PATH}/command-id/approve`,
      approval,
    );

    const cancellation = {
      expected_version: 1,
      reason_code: "owner_requested" as const,
    };
    await cancelMobileReview("command-id", cancellation);
    expect(apiClient.post).toHaveBeenCalledWith(
      `${MOBILE_ENGINEERING_PATH}/command-id/cancel`,
      cancellation,
    );
  });

  it("uses the authenticated capacity summary and versioned policy paths", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { workers: [] } });
    await getCapacitySummary();
    expect(apiClient.get).toHaveBeenCalledWith(`${ENGINEERING_CAPACITY_PATH}/summary`);

    vi.mocked(apiClient.put).mockResolvedValue({ data: { version: 2 } });
    const policy = {
      maximum_concurrent_workstreams: 2,
      maximum_per_worker: 1,
      reserved_capacity: 0,
      auto_allocate_released_capacity: false,
      expected_version: 1,
    };
    await updateCapacityPolicy(policy);
    expect(apiClient.put).toHaveBeenCalledWith(`${ENGINEERING_CAPACITY_PATH}/policy`, policy);
  });
});
