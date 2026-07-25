import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as jobsApi from "../../api/jobs";
import type { JobDetail, JobStatus } from "../../types/jobs";
import { LifecycleActionButtons } from "./LifecycleActionButtons";

vi.mock("../../api/jobs");
const base = { id: "job-1", job_number: "JOB-000001", concurrency_version: 4, priority: "normal", customer: {}, service_location: {}, appointments: [] } as unknown as JobDetail;
function renderActions(status: JobStatus) { const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } }); return render(<QueryClientProvider client={client}><LifecycleActionButtons job={{ ...base, status }} /></QueryClientProvider>); }

describe("Job lifecycle actions", () => {
  beforeEach(() => { vi.clearAllMocks(); });
  it("uses one centralized state presentation and submits the current version", async () => {
    vi.mocked(jobsApi.pauseJob).mockResolvedValue({ id: "job-1" } as never); renderActions("in_progress");
    expect(screen.getByRole("button", { name: "Pause work" })).toBeInTheDocument(); expect(screen.getByRole("button", { name: "Complete Job" })).toBeInTheDocument(); expect(screen.queryByRole("button", { name: "Activate" })).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Pause reason" }), "weather"); await userEvent.click(screen.getByRole("button", { name: "Pause work" }));
    expect(jobsApi.pauseJob).toHaveBeenCalledWith("job-1", { expected_version: 4, reason_code: "weather" });
  });
  it("confirms significant actions and renders controlled conflicts", async () => {
    vi.mocked(jobsApi.completeJob).mockRejectedValue({ response: { status: 409 }, isAxiosError: true }); renderActions("in_progress");
    await userEvent.click(screen.getByRole("button", { name: "Complete Job" }));
    expect(screen.getByRole("dialog", { name: "Complete Job JOB-000001?" })).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: "Complete Job" })[1]);
    expect(await screen.findByText("Job changed")).toBeInTheDocument();
  });
  it("prevents duplicate lifecycle submission while confirmation is pending", async () => {
    vi.mocked(jobsApi.cancelJob).mockImplementation(() => new Promise(() => undefined));
    renderActions("ready");
    await userEvent.click(screen.getByRole("button", { name: "Cancel Job" }));
    await userEvent.click(screen.getAllByRole("button", { name: "Cancel Job" })[1]);
    expect(screen.getAllByRole("button", { name: /Cancel Job/ })[1]).toBeDisabled();
    expect(jobsApi.cancelJob).toHaveBeenCalledOnce();
  });
});
