import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../../../api/client";
import {
  decideEngineeringReview,
  engineeringReviewPath,
  executeRepositoryCommit,
  getEngineeringReview,
  getRepositoryAuthorization,
  getRepositoryOperation,
  prepareEngineeringReview,
  repositoryAuthorizationPath,
  repositoryOperationPath,
  requestRepositoryAuthorization,
} from "./api";

vi.mock("../../../api/client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(apiClient.get).mockResolvedValue({ data: {} });
  vi.mocked(apiClient.post).mockResolvedValue({ data: {} });
});

describe("mobile owner-workflow API", () => {
  it("uses only the bounded review, authorization, and operation endpoints", async () => {
    await prepareEngineeringReview("command-id");
    expect(apiClient.post).toHaveBeenLastCalledWith(
      `${engineeringReviewPath}/commands/command-id`,
    );

    await getEngineeringReview("review-id");
    expect(apiClient.get).toHaveBeenLastCalledWith(
      `${engineeringReviewPath}/review-id`,
    );

    const decision = {
      expected_version: 1,
      review_digest: "a".repeat(64),
      decision: "accept" as const,
      reason_code: null,
    };
    await decideEngineeringReview("review-id", decision);
    expect(apiClient.post).toHaveBeenLastCalledWith(
      `${engineeringReviewPath}/review-id/decision`,
      decision,
    );

    const authorization = {
      review_id: "review-id",
      review_digest: "a".repeat(64),
      operation_type: "create_commit" as const,
      file_boundary: ["frontend/src/example.tsx"],
      expected_branch: "customer-management-v1",
      expected_base_commit: "b".repeat(40),
      expires_at: "2026-07-27T20:30:00Z",
      idempotency_key: "mobile-authorization-decision-id",
    };
    await requestRepositoryAuthorization(authorization);
    expect(apiClient.post).toHaveBeenLastCalledWith(
      repositoryAuthorizationPath,
      authorization,
    );

    await getRepositoryAuthorization("authorization-id");
    expect(apiClient.get).toHaveBeenLastCalledWith(
      `${repositoryAuthorizationPath}/authorization-id`,
    );

    const operation = {
      authorization_id: "authorization-id",
      capability_id: "capability-id",
      authorization_digest: "c".repeat(64),
      commit_subject: "feat(frontend): complete mobile engineering workflow",
      idempotency_key: "mobile-operation-authorization-id",
    };
    await executeRepositoryCommit(operation);
    expect(apiClient.post).toHaveBeenLastCalledWith(
      `${repositoryOperationPath}/execute`,
      operation,
    );

    await getRepositoryOperation("operation-id");
    expect(apiClient.get).toHaveBeenLastCalledWith(
      `${repositoryOperationPath}/operation-id`,
    );
  });
});
