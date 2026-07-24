import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as hooks from "./hooks";
import { MobileEngineeringDetailPage } from "./MobileEngineeringDetailPage";
import { MobileEngineeringListPage } from "./MobileEngineeringListPage";
import type { MobileReviewDetail } from "./types";

vi.mock("./hooks");

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
});

afterEach(cleanup);

describe("mobile Engineering Control", () => {
  it("renders loading, empty, error, and phone-safe pending review cards", async () => {
    vi.mocked(hooks.useMobileReviews).mockReturnValueOnce({
      isLoading: true,
    } as never);
    renderList();
    expect(
      screen.getByRole("status", { name: "Loading engineering reviews" }),
    ).toBeInTheDocument();
    cleanup();

    vi.mocked(hooks.useMobileReviews).mockReturnValueOnce({
      isLoading: false,
      data: {
        items: [],
        page: 1,
        page_size: 10,
        total_count: 0,
        total_pages: 0,
      },
    } as never);
    renderList();
    expect(
      screen.getByRole("heading", { name: "No reviews found" }),
    ).toBeInTheDocument();
    cleanup();

    const refetch = vi.fn();
    vi.mocked(hooks.useMobileReviews).mockReturnValueOnce({
      isLoading: false,
      isError: true,
      refetch,
    } as never);
    renderList();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(refetch).toHaveBeenCalledOnce();
    cleanup();

    vi.mocked(hooks.useMobileReviews).mockReturnValue({
      isLoading: false,
      data: {
        items: [review],
        page: 1,
        page_size: 10,
        total_count: 2,
        total_pages: 2,
      },
    } as never);
    renderList();
    expect(screen.getByRole("link", { name: review.ecid })).toHaveAttribute(
      "href",
      `/engineering/${review.id}`,
    );
    expect(screen.queryByText(review.owner_instruction)).not.toBeInTheDocument();
    expect(screen.getAllByText("Execution not connected")).not.toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(hooks.useMobileReviews).toHaveBeenLastCalledWith({
      page: 2,
      pageSize: 10,
    });
  });

  it("submits exact reviewed evidence only after deliberate confirmation", async () => {
    const approve = vi.fn();
    vi.mocked(hooks.useMobileReview).mockReturnValue({
      isLoading: false,
      data: review,
    } as never);
    vi.mocked(hooks.useApproveMobileReview).mockReturnValue(mutation(approve));
    renderDetail();

    expect(screen.getByText(review.owner_instruction)).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Approve command" }),
    );
    expect(
      screen.getByRole("dialog", { name: "Approve this command?" }),
    ).toBeInTheDocument();
    await userEvent.click(
      screen.getAllByRole("button", { name: "Approve command" })[1],
    );

    expect(approve).toHaveBeenCalledWith(
      {
        expected_version: review.version,
        instruction_digest: review.instruction_digest,
        request_digest: review.request_digest,
        repository_key: review.repository_key,
        expected_branch: review.expected_branch,
        expected_head: review.expected_head,
        requested_code_changes: review.requested_code_changes,
      },
      expect.any(Object),
    );
  });

  it("requires re-review after stale approval and never retries automatically", async () => {
    const approve = vi.fn((_input, options) =>
      (options as { onError: () => void }).onError(),
    );
    vi.mocked(hooks.useMobileReview).mockReturnValue({
      isLoading: false,
      data: review,
    } as never);
    vi.mocked(hooks.useApproveMobileReview).mockReturnValue(mutation(approve));
    renderDetail();

    await userEvent.click(
      screen.getByRole("button", { name: "Approve command" }),
    );
    await userEvent.click(
      screen.getAllByRole("button", { name: "Approve command" })[1],
    );
    expect(
      await screen.findByText(/changed or its evidence did not match/i),
    ).toBeInTheDocument();
    expect(approve).toHaveBeenCalledOnce();
  });

  it("confirms cancellation and keeps unsupported rejection unavailable", async () => {
    const cancel = vi.fn();
    vi.mocked(hooks.useMobileReview).mockReturnValue({
      isLoading: false,
      data: review,
    } as never);
    vi.mocked(hooks.useCancelMobileReview).mockReturnValue(mutation(cancel));
    renderDetail();

    expect(screen.getByText("Rejection is not available yet")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /reject/i })).not.toBeInTheDocument();
    await userEvent.selectOptions(
      screen.getByLabelText("Cancellation reason"),
      "scope_changed",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Cancel command" }),
    );
    await userEvent.click(
      screen.getAllByRole("button", { name: "Cancel command" })[1],
    );
    expect(cancel).toHaveBeenCalledWith(
      { expected_version: review.version, reason_code: "scope_changed" },
      expect.any(Object),
    );
  });

  it("hides lifecycle mutations when the backend marks them unavailable", () => {
    vi.mocked(hooks.useMobileReview).mockReturnValue({
      isLoading: false,
      data: {
        ...review,
        approval_state: "expired",
        can_approve: false,
        can_cancel: false,
      },
    } as never);
    renderDetail();
    expect(
      screen.queryByRole("button", { name: "Approve command" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Cancel command" }),
    ).not.toBeInTheDocument();
  });
});
