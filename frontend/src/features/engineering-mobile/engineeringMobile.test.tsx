import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as hooks from "./hooks";
import { MobileEngineeringDetailPage } from "./MobileEngineeringDetailPage";
import { MobileEngineeringListPage } from "./MobileEngineeringListPage";
import type {
  MobileReviewDetail,
  MobileWorkstreamSummary,
} from "./types";

vi.mock("./hooks");
vi.mock("./realtime", () => ({ useEngineeringRealtime: () => "live" }));

const review: MobileReviewDetail = {
  id: "3f68dc17-0be5-46d1-9666-1c7bb825be51",
  ecid: "ECID-2026-000001",
  command_type: "owner_instruction",
  owner_instruction: "Inspect only the approved Engineering files.",
  instruction_digest: "a".repeat(64),
  request_digest: "b".repeat(64),
  repository_key: "acp-enterprise",
  expected_branch: "customer-management-v1",
  expected_head: "c".repeat(40),
  requested_code_changes: true,
  approval_state: "awaiting_approval",
  execution_state: "execution_not_connected",
  execution_connected: false,
  result_reference: null,
  created_at: "2026-07-24T12:00:00Z",
  updated_at: "2026-07-24T12:00:00Z",
  expires_at: "2026-07-25T12:00:00Z",
  version: 1,
  approved_at: null,
  approved_by_user_id: null,
  canceled_at: null,
  canceled_by_user_id: null,
  cancellation_reason_code: null,
  can_approve: true,
  can_cancel: true,
};

const workstream: MobileWorkstreamSummary = {
  command_id: review.id,
  execution_id: "19366485-df36-436d-b39b-593e89c74c4c",
  ecid: review.ecid,
  display_name: "Prepare the Mission Control owner experience",
  repository_key: review.repository_key,
  expected_branch: review.expected_branch,
  expected_head: review.expected_head,
  approval_state: "approved",
  lifecycle_state: "awaiting_review",
  progress_summary: "Execution completed",
  owner_action_required: true,
  next_owner_action: "review_execution_result",
  connection_state: "disconnected",
  assigned_worker_id: "worker-id",
  offer_or_lease_state: "released",
  heartbeat_at: "2026-07-26T11:58:00Z",
  review_id: "83f7f5bc-fab3-46a5-8ce5-141dd22e7c69",
  review_state: "pending",
  authorization_id: null,
  authorization_status: null,
  repository_operation_id: null,
  repository_operation_status: null,
  failure_classification: null,
  resulting_commit_sha: null,
  repository_clean: null,
  owner_attention_required: true,
  updated_at: "2026-07-26T12:00:00Z",
  pipeline_status: "waiting_for_owner",
  desired_state: "active",
  control_pending: false,
  available_actions: ["pause", "cancel"],
  runtime_state: "waiting_for_owner",
  runtime_version: null,
  acknowledged_action: null,
  acknowledged_at: null,
  acknowledgement_expires_at: null,
  worker_health: null,
  progress_percent: null,
  current_activity: null,
  acknowledgement_latency_ms: null,
  execution_latency_ms: null,
  validation_latency_ms: null,
  deployment_latency_ms: null,
  worker_uptime_seconds: null,
  reconnect_count: 0,
};

const disconnected = {
  state: "disconnected" as const,
  session_id: null,
  last_contact_at: null,
  heartbeat_at: null,
};

const mutation = (mutate = vi.fn()) =>
  ({ mutate, isPending: false } as never);

function renderList() {
  return render(
    <MemoryRouter>
      <MobileEngineeringListPage />
    </MemoryRouter>,
  );
}

function renderDetail() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[`/engineering/${review.id}`]}>
        <Routes>
          <Route
            path="/engineering/:commandId"
            element={<MobileEngineeringDetailPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(hooks.useApproveMobileReview).mockReturnValue(mutation());
  vi.mocked(hooks.useCancelMobileReview).mockReturnValue(mutation());
  vi.mocked(hooks.useMobileCommandStatus).mockReturnValue({
    isLoading: false,
    isError: false,
    data: review,
  } as never);
  vi.mocked(hooks.useControlMobileWorkstream).mockReturnValue(mutation());
  vi.mocked(hooks.useAcknowledgeMissionNotification).mockReturnValue(mutation());
  vi.mocked(hooks.useTransitionMissionNotification).mockReturnValue(mutation());
  vi.mocked(hooks.useMissionNotifications).mockReturnValue({
    data: {
      items: [],
      unread_count: 0,
      escalated_count: 0,
      page: 1,
      page_size: 25,
      total_count: 0,
      total_pages: 0,
    },
  } as never);
  vi.mocked(hooks.usePendingMobileReviews).mockReturnValue({
    data: {
      items: [],
      page: 1,
      page_size: 10,
      total_count: 0,
      total_pages: 0,
    },
  } as never);
  vi.mocked(hooks.useMobileReview).mockReturnValue({ data: review } as never);
});

afterEach(cleanup);

describe("mobile Engineering Control", () => {
  it("renders loading, empty, error, and phone-safe workstream cards", async () => {
    vi.mocked(hooks.useMobileWorkstreams).mockReturnValueOnce({
      isLoading: true,
    } as never);
    renderList();
    expect(
      screen.getByRole("status", { name: "Opening Mission Control" }),
    ).toBeInTheDocument();
    cleanup();

    vi.mocked(hooks.useMobileWorkstreams).mockReturnValueOnce({
      isLoading: false,
      data: {
        items: [],
        connectivity: disconnected,
        page: 1,
        page_size: 10,
        total_count: 0,
        total_pages: 0,
      },
    } as never);
    renderList();
    expect(screen.getByText("No workstreams are active right now.")).toBeInTheDocument();
    cleanup();

    vi.mocked(hooks.useMobileWorkstreams).mockReturnValueOnce({
      isLoading: false,
      isError: true,
      error: { isAxiosError: true, response: { status: 401 } },
    } as never);
    renderList();
    expect(
      screen.getByRole("alert", { name: "Authentication required" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    cleanup();

    vi.mocked(hooks.useMobileWorkstreams).mockReturnValue({
      isLoading: false,
      data: {
        items: [workstream],
        connectivity: disconnected,
        page: 1,
        page_size: 10,
        total_count: 2,
        total_pages: 2,
      },
    } as never);
    renderList();
    expect(screen.getByText(workstream.display_name).closest("a")).toHaveAttribute(
      "href",
      `/engineering/${review.id}`,
    );
    expect(screen.queryByText(review.owner_instruction)).not.toBeInTheDocument();
    expect(screen.getAllByText("Needs you").length).toBeGreaterThan(0);
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Analytics/ }));
    expect(screen.getByRole("heading", { name: "Engineering analytics" })).toBeInTheDocument();
    expect(hooks.useMobileWorkstreams).toHaveBeenLastCalledWith({ page: 1, pageSize: 100 });
  });

  it("shows the pipeline and confirms owner control actions", async () => {
    const mutate = vi.fn();
    vi.mocked(hooks.useMobileWorkstream).mockReturnValue({
      isLoading: false,
      data: {
        ...workstream,
        owner_instruction: review.owner_instruction,
        requested_code_changes: true,
        created_at: review.created_at,
        started_at: "2026-07-26T11:00:00Z",
        finished_at: null,
        timeline: [{ event: "execution_started", occurred_at: "2026-07-26T11:00:00Z" }],
        runtime_state: "running",
        pipeline_status: "running",
        runtime_version: 3,
        acknowledged_action: "start",
        acknowledged_at: "2026-07-26T10:59:00Z",
        acknowledgement_expires_at: "2026-07-26T11:04:00Z",
        worker_health: "healthy",
        progress_percent: 42,
        current_activity: "Running validation",
      },
    } as never);
    vi.mocked(hooks.useControlMobileWorkstream).mockReturnValue(mutation(mutate));
    renderDetail();

    expect(screen.getByText(review.owner_instruction)).toBeInTheDocument();
    expect(screen.getByText("42% · Running validation")).toBeInTheDocument();
    expect(screen.getByText("Healthy")).toBeInTheDocument();
    expect(screen.getByRole("listitem", { current: "step" })).toHaveTextContent("Running");
    await userEvent.click(screen.getByRole("button", { name: "Pause" }));
    expect(screen.getByRole("dialog", { name: "Pause this workstream?" })).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: "Pause" })[1]);
    expect(mutate).toHaveBeenCalledWith({ action: "pause" }, expect.any(Object));
  });
});
