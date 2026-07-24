import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { EngineeringCommandDetail } from "../../types/engineeringControl";
import { EngineeringCommandDetailRoute } from "../../routes/EngineeringCommandDetailRoute";
import { EngineeringRoute } from "../../routes/EngineeringRoute";
import * as hooks from "./useEngineeringCommands";

vi.mock("./useEngineeringCommands");

const command: EngineeringCommandDetail = {
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
  created_at: "2026-07-24T12:00:00Z",
  updated_at: "2026-07-24T12:00:00Z",
  expires_at: "2026-07-25T12:00:00Z",
  version: 1,
  approved_at: null,
  approved_by_user_id: null,
  canceled_at: null,
  canceled_by_user_id: null,
  cancellation_reason_code: null,
};

const mutation = (implementation?: (input: unknown, options: unknown) => void) =>
  ({ mutate: vi.fn(implementation), isPending: false } as never);

function renderList() {
  return render(<MemoryRouter><EngineeringRoute /></MemoryRouter>);
}

function renderDetail() {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/engineering/${command.id}`]}>
        <Routes>
          <Route path="/engineering/:commandId" element={<EngineeringCommandDetailRoute />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(hooks.useApproveEngineeringCommand).mockReturnValue(mutation());
  vi.mocked(hooks.useCancelEngineeringCommand).mockReturnValue(mutation());
});

describe("Engineering Command owner workspace", () => {
  it("renders loading, empty, error with retry, and safe list content", async () => {
    vi.mocked(hooks.useEngineeringCommands).mockReturnValueOnce({ isLoading: true } as never);
    renderList();
    expect(screen.getByRole("status", { name: "Loading Engineering Commands" })).toBeInTheDocument();
    cleanup();

    vi.mocked(hooks.useEngineeringCommands).mockReturnValueOnce({
      isLoading: false, isError: false, data: { items: [], page: 1, page_size: 20, total_count: 0, total_pages: 0 },
    } as never);
    renderList();
    expect(screen.getByRole("heading", { name: "No Engineering Commands" })).toBeInTheDocument();
    cleanup();

    const refetch = vi.fn();
    vi.mocked(hooks.useEngineeringCommands).mockReturnValueOnce({ isLoading: false, isError: true, refetch } as never);
    renderList();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(refetch).toHaveBeenCalled();
    cleanup();

    vi.mocked(hooks.useEngineeringCommands).mockReturnValue({
      isLoading: false, isError: false, data: { items: [command], page: 1, page_size: 20, total_count: 2, total_pages: 2 },
    } as never);
    renderList();
    expect(screen.getByRole("link", { name: command.ecid })).toHaveAttribute("href", `/engineering/${command.id}`);
    expect(screen.getByText("Execution Not Connected")).toBeInTheDocument();
    expect(screen.queryByText(command.owner_instruction)).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Approval status"), "approved");
    expect(vi.mocked(hooks.useEngineeringCommands)).toHaveBeenLastCalledWith(expect.objectContaining({ approvalState: "approved", page: 1 }));
    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(vi.mocked(hooks.useEngineeringCommands)).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }));
  });

  it("submits exact approval evidence and never suggests execution started", async () => {
    const mutate = vi.fn();
    vi.mocked(hooks.useEngineeringCommand).mockReturnValue({ isLoading: false, isError: false, data: command } as never);
    vi.mocked(hooks.useApproveEngineeringCommand).mockReturnValue({ mutate, isPending: false } as never);
    renderDetail();
    expect(screen.getByText(command.owner_instruction)).toBeInTheDocument();
    expect(screen.getAllByText("Execution not connected").length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole("button", { name: "Approve command" }));
    expect(screen.getByRole("dialog", { name: "Approve this Engineering Command?" })).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: "Approve command" })[1]);
    expect(mutate).toHaveBeenCalledWith({
      expected_version: command.version,
      instruction_digest: command.instruction_digest,
      request_digest: command.request_digest,
      repository_key: command.repository_key,
      expected_branch: command.expected_branch,
      expected_head: command.expected_head,
      requested_code_changes: true,
    }, expect.any(Object));
  });

  it("requires re-review on approval failure and confirms controlled cancellation", async () => {
    const approveMutate = vi.fn((_input, options) => (options as { onError: () => void }).onError());
    const cancelMutate = vi.fn();
    vi.mocked(hooks.useEngineeringCommand).mockReturnValue({ isLoading: false, isError: false, data: command } as never);
    vi.mocked(hooks.useApproveEngineeringCommand).mockReturnValue({ mutate: approveMutate, isPending: false } as never);
    vi.mocked(hooks.useCancelEngineeringCommand).mockReturnValue({ mutate: cancelMutate, isPending: false } as never);
    renderDetail();
    await userEvent.click(screen.getByRole("button", { name: "Approve command" }));
    await userEvent.click(screen.getAllByRole("button", { name: "Approve command" })[1]);
    expect(await screen.findByText(/command changed or its evidence did not match/i)).toBeInTheDocument();
    expect(approveMutate).toHaveBeenCalledTimes(1);

    await userEvent.selectOptions(screen.getByLabelText("Cancel command"), "scope_changed");
    await userEvent.click(screen.getByRole("button", { name: "Cancel command" }));
    expect(screen.getByRole("dialog", { name: "Cancel this Engineering Command?" })).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: "Cancel command" })[1]);
    expect(cancelMutate).toHaveBeenCalledWith(
      { expected_version: 1, reason_code: "scope_changed" },
      expect.any(Object),
    );
  });

  it("hides lifecycle actions for terminal commands and renders error retry", async () => {
    vi.mocked(hooks.useEngineeringCommand).mockReturnValueOnce({
      isLoading: false, isError: false, data: { ...command, approval_state: "expired" },
    } as never);
    const view = renderDetail();
    expect(screen.queryByRole("button", { name: "Approve command" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel command" })).not.toBeInTheDocument();
    view.unmount();

    const refetch = vi.fn();
    vi.mocked(hooks.useEngineeringCommand).mockReturnValue({ isLoading: false, isError: true, refetch } as never);
    renderDetail();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(refetch).toHaveBeenCalled();
  });
});
