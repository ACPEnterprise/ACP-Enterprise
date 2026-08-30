import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as hooks from "./hooks";
import { MobileEngineeringDetailPage } from "./MobileEngineeringDetailPage";
import { MobileEngineeringListPage } from "./MobileEngineeringListPage";
import { milestoneDisplayStatus } from "./presentation";
import type { MobileReviewDetail, MobileWorkstreamSummary } from "./types";

vi.mock("./hooks");
vi.mock("./realtime", () => ({ useEngineeringRealtime: () => "live" }));
const permissions = new Set<string>();
vi.mock("../../auth", () => ({
  useHasPermission: (code: string) => permissions.has(code),
}));

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

const mutation = (mutate = vi.fn()) => ({ mutate, isPending: false }) as never;

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
  permissions.clear();
  permissions.add("COMPANY_ENGINEERING_COMMAND_READ");
  permissions.add("COMPANY_ENGINEERING_COMMAND_MANAGE");
  permissions.add("COMPANY_ENGINEERING_COMMAND_APPROVE");
  permissions.add("COMPANY_ENGINEERING_CAPACITY_READ");
  vi.mocked(hooks.useApproveMobileReview).mockReturnValue(mutation());
  vi.mocked(hooks.useCancelMobileReview).mockReturnValue(mutation());
  vi.mocked(hooks.useDecideEngineeringReview).mockReturnValue(mutation());
  vi.mocked(hooks.useEngineeringCapacity).mockReturnValue({
    isLoading: false,
    isError: false,
    data: {
      policy: null,
      configured_capacity: 0,
      allocated_capacity: 0,
      reserved_capacity: 0,
      numeric_available_capacity: 0,
      available_capacity: 0,
      offline_workers: 0,
      unhealthy_workers: 0,
      reconciliation_required: 0,
      workers: [],
      eligible_workers: [],
      machines: [],
      active_reservations: [],
      active_allocations: [],
      waiting_workstreams: [],
    },
  } as never);
  vi.mocked(hooks.useCapacityMutation).mockReturnValue(mutation());
  vi.mocked(hooks.useWorkerLimitMutation).mockReturnValue(mutation());
  vi.mocked(hooks.useExistingWorkerSetupMutation).mockReturnValue(mutation());
  vi.mocked(hooks.useWorkerStateMutation).mockReturnValue(mutation());
  vi.mocked(hooks.useReservationMutation).mockReturnValue(mutation());
  vi.mocked(hooks.useReservationReleaseMutation).mockReturnValue(mutation());
  vi.mocked(hooks.useAllocationReleaseMutation).mockReturnValue(mutation());
  vi.mocked(hooks.useAllocationReconciliationMutation).mockReturnValue(mutation());
  vi.mocked(hooks.useMobileCommandStatus).mockReturnValue({
    isLoading: false,
    isError: false,
    data: review,
  } as never);
  vi.mocked(hooks.useControlMobileWorkstream).mockReturnValue(mutation());
  vi.mocked(hooks.useAcknowledgeMissionNotification).mockReturnValue(
    mutation(),
  );
  vi.mocked(hooks.useTransitionMissionNotification).mockReturnValue(mutation());
  vi.mocked(hooks.useMilestoneAction).mockReturnValue(mutation());
  vi.mocked(hooks.useRoadmaps).mockReturnValue({
    data: {
      roadmaps: [],
      milestones: [],
      waiting_for_me: [],
      owner_attention: [],
      running_milestones: [],
      dependency_waiting_milestones: [],
      capacity_waiting_milestones: [],
      external_work_milestones: [],
      completed_recently: [],
      current_milestones: [],
      next_approved_milestones: [],
      future_milestones: [],
      completed_milestones: [],
      blocked_milestones: [],
      actionable_count: 0,
    },
  } as never);
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
  it("shows validation failure instead of nominal Ready while revision controls", () => {
    expect(milestoneDisplayStatus({
      status: "ready",
      attention_reason: "Required validation failed. Revision available; no work was published.",
      available_owner_actions: ["request_revision", "cancel"],
    })).toBe("Validation Failed");
  });

  it("shows exactly the actionable milestone and dispatches it without a prompt", async () => {
    const mutate = vi.fn();
    const milestone = {
      id: "f58de32e-bf42-43ac-857d-17ffeb0c2bb2",
      roadmap_id: "dd37ad9f-f32a-4dd7-9cb5-f25cf63a4870",
      position: 2,
      title: "Owner milestone dispatch",
      milestone_code: "TEST.2",
      scheduler_version: "TEST.1",
      permanent_capacity_identity: "OM1",
      readiness_state: "ready",
      reconciliation_state: "current",
      objective: "Send the approved definition directly to Engineering Execution.",
      owning_workstream: "Mission Control",
      owning_branch: "mission-control-v2.1",
      authority: ["Milestone authority"],
      constraints: ["Do not redesign transport"],
      dependencies: ["Mission Control V2"],
      validation: ["Run integration tests"],
      deliverables: ["Dispatcher"],
      stop_conditions: ["Unrecoverable blocker"],
      expected_completion_evidence: ["Structured result"],
      status: "ready" as const,
      definition_approved: true,
      requested_code_changes: true,
      attention_class: "owner_action_required" as const,
      attention_reason: "This milestone is ready to start.",
      available_owner_actions: ["start", "skip"] as const,
      external_evidence: null,
      command_id: null,
      version: 3,
      started_at: null,
      completed_at: null,
      reviewed_at: null,
      created_at: "2026-07-31T12:00:00Z",
      updated_at: "2026-07-31T12:00:00Z",
    };
    vi.mocked(hooks.useMilestoneAction).mockReturnValue(mutation(mutate));
    vi.mocked(hooks.useRoadmaps).mockReturnValue({
      data: {
        roadmaps: [{ id: milestone.roadmap_id, title: "Mission Control", repository_key: "acp-enterprise", expected_branch: "mission-control-v2", expected_head: "a".repeat(40), status: "active", version: 1, created_at: milestone.created_at, updated_at: milestone.updated_at }],
        milestones: [milestone],
        waiting_for_me: [milestone],
        owner_attention: [milestone],
        running_milestones: [],
        dependency_waiting_milestones: [],
        capacity_waiting_milestones: [],
        external_work_milestones: [],
        completed_recently: [],
        current_milestones: [milestone],
        next_approved_milestones: [],
        future_milestones: [],
        completed_milestones: [],
        blocked_milestones: [],
        actionable_count: 1,
      },
    } as never);
    vi.mocked(hooks.useMobileWorkstreams).mockReturnValue({ isLoading: false, data: { items: [], connectivity: disconnected, page: 1, page_size: 100, total_count: 0, total_pages: 0 } } as never);
    renderList();
    await userEvent.click(screen.getByRole("button", { name: /Roadmap/ }));
    expect(screen.getAllByText("Owner milestone dispatch").length).toBeGreaterThan(0);
    expect(screen.getAllByText("TEST.2").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Mission Control · mission-control-v2.1 · OM1/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Ready · Reconciliation: Current/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("1").length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole("button", { name: "Start next milestone" }));
    expect(mutate).toHaveBeenCalledWith(
      { id: milestone.id, version: 3, action: "start" },
      expect.any(Object),
    );
  });

  it("renders phone-safe capacity truth and owner controls", async () => {
    vi.mocked(hooks.useMobileWorkstreams).mockReturnValue({
      isLoading: false,
      data: { items: [], connectivity: disconnected, page: 1, page_size: 10, total_count: 0, total_pages: 0 },
    } as never);
    vi.mocked(hooks.useEngineeringCapacity).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        policy: { id: "policy", maximum_concurrent_workstreams: 2, maximum_per_worker: 1, reserved_capacity: 0, auto_allocate_released_capacity: false, version: 1, updated_at: "2026-08-03T12:00:00Z" },
        configured_capacity: 2,
        allocated_capacity: 1,
        reserved_capacity: 0,
        numeric_available_capacity: 1,
        available_capacity: 1,
        offline_workers: 0,
        unhealthy_workers: 0,
        reconciliation_required: 0,
        workers: [{ id: "capacity", worker_id: "worker", machine_id: "machine", machine_label: "Original Office Machine", configured_limit: 1, allocated_capacity: 1, reserved_capacity: 0, available_capacity: 0, operational_state: "occupied", health_state: "healthy", last_reconciled_at: null, version: 1 }],
        eligible_workers: [],
        machines: [{ id: "planned", machine_label: "Laptop 1", expected_available_on: "2026-08-04", enrollment_state: "unenrolled", worker_id: null }],
        active_reservations: [],
        active_allocations: [],
        waiting_workstreams: [],
      },
    } as never);
    renderList();
    await userEvent.click(screen.getByRole("button", { name: /Capacity/ }));
    expect(screen.getByRole("heading", { name: "Machines and assignments" })).toBeInTheDocument();
    expect(screen.getByText("Original Office Machine")).toBeInTheDocument();
    expect(screen.getByText("Laptop 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save capacity limits" })).toHaveClass("min-h-11");
    expect(screen.getByRole("button", { name: "Pause capacity" })).toHaveClass("min-h-11");
  });

  it("puts trusted worker setup before a bounded waiting queue on phone", async () => {
    const configure = vi.fn();
    vi.mocked(hooks.useExistingWorkerSetupMutation).mockReturnValue(mutation(configure));
    vi.mocked(hooks.useMobileWorkstreams).mockReturnValue({
      isLoading: false,
      data: { items: [], connectivity: disconnected, page: 1, page_size: 10, total_count: 0, total_pages: 0 },
    } as never);
    vi.mocked(hooks.useEngineeringCapacity).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        policy: { id: "policy", maximum_concurrent_workstreams: 2, maximum_per_worker: 1, reserved_capacity: 0, auto_allocate_released_capacity: false, version: 2, updated_at: "2026-08-03T12:00:00Z" },
        configured_capacity: 0,
        allocated_capacity: 0,
        reserved_capacity: 0,
        numeric_available_capacity: 0,
        available_capacity: 0,
        offline_workers: 0,
        unhealthy_workers: 0,
        reconciliation_required: 0,
        workers: [],
        eligible_workers: [{ worker_id: "trusted-worker", worker_name: "ACP Office Engineering Node", provider_identifier: "controlled-provider", lifecycle_state: "available", identity_id: "identity", identity_name: "Office node identity", last_heartbeat_at: "2026-08-03T12:00:00Z", health_state: "healthy", capacity_configured: false }],
        machines: [],
        active_reservations: [],
        active_allocations: [],
        waiting_workstreams: Array.from({ length: 8 }, (_, index) => ({ command_id: `command-${index}`, ecid: `ECID-2026-${index}`, repository_key: "acp-enterprise", expected_branch: "customer-management-v1", milestone_id: `milestone-${index}`, milestone_title: `Milestone ${index}`, milestone_position: index + 1, workstream: "Operations", roadmap_title: "Operations", owning_branch: "customer-management-v1", identity_state: "resolved", assigned_worker_id: null, assigned_worker_name: null, machine_label: null, capacity_amount: 1, requested_at: "2026-08-03T12:00:00Z", decision: "blocked_by_worker_health", reason: "No healthy operational worker has configured capacity." })),
      },
    } as never);

    renderList();
    await userEvent.click(screen.getByRole("button", { name: /Capacity/ }));
    const workersHeading = screen.getByRole("heading", { name: "Workers and machines" });
    const queueHeading = screen.getByRole("heading", { name: "Waiting for capacity" });
    expect(workersHeading.compareDocumentPosition(queueHeading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByLabelText("ACP Office Engineering Node machine label")).toHaveValue("ACP Office Engineering Node");
    expect(screen.getAllByText(/ECID-2026-/)).toHaveLength(5);
    expect(screen.getByRole("button", { name: "Show all 8 waiting workstreams" })).toBeInTheDocument();

    await userEvent.clear(screen.getByLabelText("ACP Office Engineering Node machine label"));
    await userEvent.type(screen.getByLabelText("ACP Office Engineering Node machine label"), "Original Office Machine");
    await userEvent.click(screen.getByRole("button", { name: "Add to capacity" }));
    expect(configure).toHaveBeenCalledWith({
      worker: expect.objectContaining({ worker_id: "trusted-worker" }),
      machineLabel: "Original Office Machine",
      configuredLimit: 1,
    });
  });

  it("identifies a milestone and confirms its exact capacity reservation", async () => {
    const reserve = vi.fn();
    vi.mocked(hooks.useReservationMutation).mockReturnValue(mutation(reserve));
    vi.mocked(hooks.useMobileWorkstreams).mockReturnValue({
      isLoading: false,
      data: { items: [], connectivity: disconnected, page: 1, page_size: 10, total_count: 0, total_pages: 0 },
    } as never);
    const queueItem = {
      command_id: "command-bea6",
      ecid: "ECID-2026-000006",
      repository_key: "acp-enterprise",
      expected_branch: "customer-management-v1",
      milestone_id: "milestone-bea6",
      milestone_title: "BEA.6 Economics Signal Definitions",
      milestone_position: 6,
      workstream: "Beacon",
      roadmap_title: "Beacon",
      owning_branch: "customer-management-v1",
      identity_state: "resolved",
      assigned_worker_id: "office-worker",
      assigned_worker_name: "ACP Office Engineering Node",
      machine_label: "ACP Office Engineering Node",
      capacity_amount: 1,
      requested_at: "2026-08-03T12:00:00Z",
      decision: "capacity_available",
      reason: "Healthy configured capacity is available; explicit dispatch remains required.",
    } as const;
    vi.mocked(hooks.useEngineeringCapacity).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        policy: { id: "policy", maximum_concurrent_workstreams: 2, maximum_per_worker: 1, reserved_capacity: 0, auto_allocate_released_capacity: false, version: 2, updated_at: "2026-08-03T12:00:00Z" },
        configured_capacity: 1,
        allocated_capacity: 0,
        reserved_capacity: 0,
        numeric_available_capacity: 1,
        available_capacity: 1,
        offline_workers: 0,
        unhealthy_workers: 0,
        reconciliation_required: 0,
        workers: [],
        eligible_workers: [],
        machines: [],
        active_reservations: [],
        active_allocations: [],
        waiting_workstreams: [queueItem],
      },
    } as never);

    renderList();
    await userEvent.click(screen.getByRole("button", { name: /Capacity/ }));
    expect(screen.getByText("BEA.6 Economics Signal Definitions")).toBeInTheDocument();
    expect(screen.getByText("Beacon · Roadmap step 6")).toBeInTheDocument();
    expect(screen.getByText("Branch: customer-management-v1")).toBeInTheDocument();
    expect(screen.getByText("Engineering Command: ECID-2026-000006")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Reserve capacity" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("ACP Office Engineering Node");
    expect(screen.getByRole("dialog")).toHaveTextContent("Reservation does not start execution");
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Reserve capacity" }));
    expect(reserve).toHaveBeenCalledWith(queueItem, expect.any(Object));
  });

  it("fails closed when a queued command has no unambiguous milestone", async () => {
    vi.mocked(hooks.useMobileWorkstreams).mockReturnValue({ isLoading: false, data: { items: [], connectivity: disconnected, page: 1, page_size: 10, total_count: 0, total_pages: 0 } } as never);
    vi.mocked(hooks.useEngineeringCapacity).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        policy: null, configured_capacity: 0, allocated_capacity: 0, reserved_capacity: 0, numeric_available_capacity: 0, available_capacity: 0, offline_workers: 0, unhealthy_workers: 0, reconciliation_required: 1, workers: [], eligible_workers: [], machines: [], active_reservations: [], active_allocations: [],
        waiting_workstreams: [{ command_id: "ambiguous", ecid: "ECID-2026-000099", repository_key: "acp-enterprise", expected_branch: "customer-management-v1", milestone_id: null, milestone_title: null, milestone_position: null, workstream: null, roadmap_title: null, owning_branch: null, identity_state: "reconciliation_required", assigned_worker_id: null, assigned_worker_name: null, machine_label: null, capacity_amount: 1, requested_at: "2026-08-03T12:00:00Z", decision: "reconciliation_required", reason: "Milestone identity must be reconciled." }],
      },
    } as never);
    renderList();
    await userEvent.click(screen.getByRole("button", { name: /Capacity/ }));
    expect(screen.getByText("Milestone identity unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reserve capacity" })).toBeDisabled();
  });

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
    expect(
      screen.getByText("No workstreams are active right now."),
    ).toBeInTheDocument();
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
    expect(
      screen.queryByRole("button", { name: "Retry" }),
    ).not.toBeInTheDocument();
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
    expect(
      screen.getByText(workstream.display_name).closest("a"),
    ).toHaveAttribute("href", `/engineering/${review.id}`);
    expect(
      screen.queryByText(review.owner_instruction),
    ).not.toBeInTheDocument();
    expect(screen.getAllByText("Needs you").length).toBeGreaterThan(0);
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Analytics/ }));
    expect(
      screen.getByRole("heading", { name: "Engineering analytics" }),
    ).toBeInTheDocument();
    expect(hooks.useMobileWorkstreams).toHaveBeenLastCalledWith(
      { page: 1, pageSize: 100 },
      true,
    );
  });

  it("does not mount Engineering reads without command-read authority", () => {
    permissions.clear();
    vi.mocked(hooks.useMobileWorkstreams).mockReturnValue({
      data: undefined, isLoading: false, isError: false,
    } as never);

    renderList();

    expect(hooks.useMobileWorkstreams).toHaveBeenCalledWith(
      { page: 1, pageSize: 100 }, false,
    );
    expect(hooks.useMissionNotifications).toHaveBeenCalledWith(false);
    expect(hooks.usePendingMobileReviews).toHaveBeenCalledWith(false);
    expect(hooks.useRoadmaps).toHaveBeenCalledWith(false);
    expect(screen.getByText(/not authorized to view Engineering Control/i)).toBeInTheDocument();
  });

  it("does not mount direct Engineering object reads without command-read authority", () => {
    permissions.clear();
    vi.mocked(hooks.useMobileWorkstream).mockReturnValue({
      data: undefined, isLoading: false, isError: false,
    } as never);

    renderDetail();

    expect(hooks.useMobileWorkstream).toHaveBeenCalledWith(review.id, false);
    expect(hooks.useMobileReview).toHaveBeenCalledWith(review.id, false);
    expect(screen.getByText(/not authorized to view this Engineering workstream/i)).toBeInTheDocument();
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
        timeline: [
          { event: "execution_started", occurred_at: "2026-07-26T11:00:00Z" },
        ],
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
    vi.mocked(hooks.useControlMobileWorkstream).mockReturnValue(
      mutation(mutate),
    );
    renderDetail();

    expect(screen.getByText(review.owner_instruction)).toBeInTheDocument();
    expect(screen.getByText("42% · Running validation")).toBeInTheDocument();
    expect(screen.getByText("Healthy")).toBeInTheDocument();
    expect(screen.getByRole("listitem", { current: "step" })).toHaveTextContent(
      "Running",
    );
    await userEvent.click(screen.getByRole("button", { name: "Pause" }));
    expect(
      screen.getByRole("dialog", { name: "Pause this workstream?" }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: "Pause" })[1]);
    expect(mutate).toHaveBeenCalledWith(
      { action: "pause" },
      expect.any(Object),
    );
  });

  it("keeps Engineering evidence read-only without manage or approve authority", () => {
    permissions.clear();
    permissions.add("COMPANY_ENGINEERING_COMMAND_READ");
    vi.mocked(hooks.useMobileWorkstream).mockReturnValue({
      isLoading: false,
      data: {
        ...workstream,
        owner_instruction: review.owner_instruction,
        requested_code_changes: true,
        created_at: review.created_at,
        timeline: [],
        available_actions: ["pause", "cancel"],
        owner_review_action_available: true,
        owner_review_digest: "d".repeat(64),
        owner_review_version: 1,
      },
    } as never);
    vi.mocked(hooks.useMobileReview).mockReturnValue({
      data: { ...review, can_approve: true },
    } as never);

    renderDetail();

    expect(screen.getByText(review.owner_instruction)).toBeInTheDocument();
    for (const name of ["Pause", "Cancel", "Approve", "Request revision", "Reject", "Review and accept published result"]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
  });

  it("shows authoritative adopted-result review detail without stale pending stages", async () => {
    const decide = vi.fn();
    vi.mocked(hooks.useDecideEngineeringReview).mockReturnValue(mutation(decide));
    vi.mocked(hooks.useMobileReview).mockReturnValue({ data: null } as never);
    vi.mocked(hooks.useMobileWorkstream).mockReturnValue({
      isLoading: false,
      data: {
        ...workstream,
        owner_instruction: "# TECH.1\n- Establish technician shell",
        requested_code_changes: true,
        created_at: review.created_at,
        started_at: "2026-08-26T18:02:00Z",
        finished_at: "2026-08-26T18:24:08Z",
        timeline: [{ event: "execution_failed", occurred_at: "2026-08-26T18:25:00Z" }],
        available_actions: [],
        runtime_state: "waiting_for_owner",
        pipeline_status: "waiting_for_owner",
        worker_health: "healthy",
        progress_percent: 100,
        current_activity: "Published result ready for owner review",
        result_commit_sha: "72a741287a8df991e8bff3a60bbcc6300a5ad76b",
        result_publication_status: "published",
        result_adoption_status: "adopted",
        result_completed_at: "2026-08-26T18:24:08Z",
        result_adopted_at: "2026-08-26T22:35:15Z",
        acknowledgement_status: "completed_from_immutable_evidence",
        execution_status: "completed",
        validation_status: "completed",
        preview_deployment_status: "not_performed",
        owner_review_digest: "d".repeat(64),
        owner_review_version: 1,
        owner_review_action_available: true,
        historical_recovery_context: [{
          classification: "historical_transport_recovery",
          summary: "Terminal transport required evidence adoption.",
          reason_code: "expired_lease_unresolved_provider_outcome",
        }],
      },
    } as never);

    renderDetail();

    expect(screen.getByText("TECH.1")).toBeInTheDocument();
    expect(screen.getByText("Establish technician shell")).toBeInTheDocument();
    expect(screen.getByText("72a741287a8df991e8bff3a60bbcc6300a5ad76b")).toBeInTheDocument();
    expect(screen.getAllByText("Completed").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("Not performed by this execution")).toHaveLength(2);
    expect(screen.getByText("Historical recovery context")).toBeInTheDocument();
    expect(screen.queryByText("Request revision")).not.toBeInTheDocument();
    expect(screen.queryByText("Pending")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Review and accept published result" }));
    const dialog = screen.getByRole("dialog", { name: "Accept this published result?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Accept published result" }));
    expect(decide).toHaveBeenCalledWith({
      expected_version: 1,
      review_digest: "d".repeat(64),
      decision: "accept",
    }, expect.any(Object));
  });
});
