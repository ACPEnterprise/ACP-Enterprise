import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { MobileExecutionStatus } from "../execution/types";
import { EngineeringOwnerWorkflow } from "./EngineeringOwnerWorkflow";
import * as hooks from "./hooks";
import type {
  EngineeringReviewPackage,
  RepositoryAuthorizationDetail,
} from "./types";

vi.mock("./hooks");

const status: MobileExecutionStatus = {
  command_id: "command-id",
  ecid: "ECID-2026-000001",
  approval_state: "approved",
  monitoring_state: "completed",
  execution_available: true,
  execution_connected: false,
  connection_state: "disconnected",
  transport_health: "unavailable",
  execution_id: "execution-id",
  execution_state: "completed",
  execution_status: "completed",
  progress_label: "Completed",
  requested_at: "2026-07-27T18:00:00Z",
  started_at: "2026-07-27T18:01:00Z",
  finished_at: "2026-07-27T18:02:00Z",
  updated_at: "2026-07-27T18:02:00Z",
  lease: {
    availability: "unavailable",
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
    availability: "available",
    status: "succeeded",
    validation_available: true,
    evidence_available: true,
    output_reference_count: 1,
    failure_classification: null,
    created_at: "2026-07-27T18:02:00Z",
  },
  review_available: true,
  review_id: "review-id",
  review_state: "pending",
  review_version: 1,
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
  timeline: [],
  terminal: true,
  polling_after_seconds: null,
};

const review: EngineeringReviewPackage = {
  review: {
    id: "review-id",
    command_id: status.command_id,
    execution_id: "execution-id",
    provider_identifier: "codex",
    review_digest: "a".repeat(64),
    state: "pending",
    version: 1,
    created_at: "2026-07-27T18:03:00Z",
    updated_at: "2026-07-27T18:03:00Z",
    decided_at: null,
  },
  ecid: status.ecid,
  command_type: "owner_instruction",
  owner_instruction: "Apply the reviewed mobile workflow.",
  requested_code_changes: true,
  repository_key: "acp-enterprise",
  expected_branch: "customer-management-v1",
  expected_head: "b".repeat(40),
  result_status: "succeeded",
  result_disposition: "accepted",
  evidence_summary: { validation: "passed" },
  validation_summary: {
    file_boundary: [
      "frontend/src/features/engineering-mobile/owner-workflow/types.ts",
    ],
  },
  output_references: [],
  failure_classification: null,
  repository_mutated: false,
  result_received_at: "2026-07-27T18:02:00Z",
  decision: null,
};

const authorization: RepositoryAuthorizationDetail = {
  id: "authorization-id",
  command_id: status.command_id,
  review_id: review.review.id,
  operation_type: "create_commit",
  expected_branch: review.expected_branch,
  expected_base_commit: review.expected_head,
  state: "authorized",
  version: 1,
  authorized_at: "2026-07-27T18:04:00Z",
  expires_at: "2026-07-27T18:34:00Z",
  revoked_at: null,
  consumed_at: null,
  capability_id: "capability-id",
  execution_id: "execution-id",
  result_id: "result-id",
  review_decision_id: "decision-id",
  file_boundary: [
    "frontend/src/features/engineering-mobile/owner-workflow/types.ts",
  ],
  review_digest: review.review.review_digest,
  authorization_digest: "c".repeat(64),
  authorization_eligible: true,
};

const mutation = (mutate = vi.fn()) =>
  ({ mutate, isPending: false, isError: false } as never);
const query = (data?: unknown) =>
  ({
    data,
    isLoading: false,
    isError: false,
  }) as never;

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(hooks.usePrepareEngineeringReview).mockReturnValue(mutation());
  vi.mocked(hooks.useEngineeringOwnerReview).mockReturnValue(query(review));
  vi.mocked(hooks.useDecideEngineeringReview).mockReturnValue(mutation());
  vi.mocked(hooks.useRequestRepositoryAuthorization).mockReturnValue(mutation());
  vi.mocked(hooks.useRepositoryAuthorization).mockReturnValue(query());
  vi.mocked(hooks.useExecuteRepositoryCommit).mockReturnValue(mutation());
  vi.mocked(hooks.useRepositoryOperation).mockReturnValue(query());
});

afterEach(cleanup);

describe("EngineeringOwnerWorkflow", () => {
  it("shows immutable evidence and requires confirmation before acceptance", async () => {
    const decide = vi.fn();
    vi.mocked(hooks.useDecideEngineeringReview).mockReturnValue(
      mutation(decide),
    );
    render(<EngineeringOwnerWorkflow commandId={status.command_id} status={status} />);

    expect(screen.getByText("Structured review package")).toBeInTheDocument();
    expect(screen.getByText("No")).toBeInTheDocument();
    expect(
      screen.getByText(
        "frontend/src/features/engineering-mobile/owner-workflow/types.ts",
      ),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Accept result" }));
    expect(decide).not.toHaveBeenCalled();
    await userEvent.click(
      screen.getAllByRole("button", { name: "Accept result" })[1],
    );
    expect(decide).toHaveBeenCalledWith(
      {
        expected_version: 1,
        review_digest: review.review.review_digest,
        decision: "accept",
        reason_code: null,
      },
      expect.any(Object),
    );
  });

  it("binds authorization to accepted review evidence", async () => {
    const requestAuthorization = vi.fn();
    vi.mocked(hooks.useEngineeringOwnerReview).mockReturnValue(
      query({
        ...review,
        review: { ...review.review, state: "accepted", version: 2 },
        decision: {
          id: "decision-id",
          reviewer_user_id: "user-id",
          decision: "accept",
          review_digest: review.review.review_digest,
          reason_code: null,
          decided_at: "2026-07-27T18:04:00Z",
        },
      }),
    );
    vi.mocked(hooks.useRequestRepositoryAuthorization).mockReturnValue(
      mutation(requestAuthorization),
    );
    render(
      <EngineeringOwnerWorkflow
        commandId={status.command_id}
        status={{ ...status, review_state: "accepted", review_version: 2 }}
      />,
    );

    await userEvent.click(
      screen.getByRole("button", { name: "Authorize one commit" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Authorize commit" }),
    );
    expect(requestAuthorization).toHaveBeenCalledWith(
      expect.objectContaining({
        review_id: review.review.id,
        review_digest: review.review.review_digest,
        operation_type: "create_commit",
        file_boundary: [
          "frontend/src/features/engineering-mobile/owner-workflow/types.ts",
        ],
        expected_branch: review.expected_branch,
        expected_base_commit: review.expected_head,
        idempotency_key: "mobile-authorization-decision-id",
      }),
      expect.any(Object),
    );
  });

  it("requires a valid immutable subject before one bounded commit", async () => {
    const execute = vi.fn();
    vi.mocked(hooks.useRepositoryAuthorization).mockReturnValue(
      query(authorization),
    );
    vi.mocked(hooks.useExecuteRepositoryCommit).mockReturnValue(
      mutation(execute),
    );
    render(
      <EngineeringOwnerWorkflow
        commandId={status.command_id}
        status={{
          ...status,
          review_state: "accepted",
          authorization_id: authorization.id,
          authorization_status: "authorized",
          authorization_eligible: true,
          repository_operation_eligible: true,
        }}
      />,
    );

    const create = screen.getByRole("button", {
      name: "Create authorized commit",
    });
    expect(create).toBeDisabled();
    await userEvent.type(
      screen.getByLabelText("Approved commit subject"),
      "feat(frontend): complete mobile engineering workflow",
    );
    expect(create).toBeEnabled();
    await userEvent.click(create);
    expect(execute).not.toHaveBeenCalled();
    await userEvent.click(
      screen.getByRole("button", { name: "Create commit" }),
    );
    expect(execute).toHaveBeenCalledWith(
      {
        authorization_id: authorization.id,
        capability_id: authorization.capability_id,
        authorization_digest: authorization.authorization_digest,
        commit_subject: "feat(frontend): complete mobile engineering workflow",
        idempotency_key: `mobile-operation-${authorization.id}`,
      },
      expect.any(Object),
    );
  });

  it("shows durable success and reconciliation without retry controls", () => {
    const { rerender } = render(
      <EngineeringOwnerWorkflow
        commandId={status.command_id}
        status={{
          ...status,
          repository_operation_id: "operation-id",
          repository_operation_status: "succeeded",
          repository_operation_resulting_commit_sha: "d".repeat(40),
        }}
      />,
    );
    expect(
      screen.getByText(/was created and the authorization was consumed/i),
    ).toBeInTheDocument();

    rerender(
      <EngineeringOwnerWorkflow
        commandId={status.command_id}
        status={{
          ...status,
          repository_operation_id: "operation-id",
          repository_operation_status: "reconciliation_required",
          repository_operation_owner_attention_required: true,
        }}
      />,
    );
    expect(screen.getByText(/No automatic retry will run/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /retry/i })).toBeNull();
  });
});
