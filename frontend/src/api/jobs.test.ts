import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import { activateJob, cancelJob, completeJob, createJob, createJobFromAppointment, getJob, listJobs, pauseJob, reopenJob, resumeJob, startJob } from "./jobs";

vi.mock("./client", () => ({ apiClient: { get: vi.fn(), post: vi.fn() } }));
const get = vi.mocked(apiClient.get); const post = vi.mocked(apiClient.post);

describe("Jobs API", () => {
  beforeEach(() => vi.clearAllMocks());
  it("maps list filters and detail to the canonical endpoint", async () => {
    get.mockResolvedValueOnce({ data: { items: [], page: 2, page_size: 20, total_count: 0, total_pages: 0 } });
    await listJobs({ searchText: " boiler ", status: ["ready"], priority: ["urgent"], jobType: ["repair"], branchId: "branch-1", page: 2, pageSize: 20, sortField: "priority", sortDirection: "asc" });
    expect(get).toHaveBeenCalledWith("/api/v1/jobs", { params: expect.objectContaining({ search_text: " boiler ", status: ["ready"], priority: ["urgent"], branch_id: "branch-1", page: 2 }) });
    get.mockResolvedValueOnce({ data: { id: "job-1" } }); await getJob("job-1");
    expect(get).toHaveBeenLastCalledWith("/api/v1/jobs/job-1");
  });
  it("uses one canonical URL family for create and lifecycle requests", async () => {
    post.mockResolvedValue({ data: { id: "job-1" } });
    await createJob({ branch_id: "b", customer_id: "c", service_location_id: "l" });
    await activateJob("job-1", { expected_version: 1 }); await startJob("job-1", { expected_version: 2 });
    await pauseJob("job-1", { expected_version: 3, reason_code: "weather" }); await resumeJob("job-1", { expected_version: 4 });
    await completeJob("job-1", { expected_version: 5 }); await cancelJob("job-1", { expected_version: 1, reason_code: "duplicate" });
    await reopenJob("job-1", { expected_version: 6, reason_code: "correction_required" });
    expect(post.mock.calls.map(([url]) => url)).toEqual(["/api/v1/jobs", "/api/v1/jobs/job-1/activate", "/api/v1/jobs/job-1/start", "/api/v1/jobs/job-1/pause", "/api/v1/jobs/job-1/resume", "/api/v1/jobs/job-1/complete", "/api/v1/jobs/job-1/cancel", "/api/v1/jobs/job-1/reopen"]);
  });
  it("uses the Jobs-owned create-from-Appointment endpoint and relationship filter", async () => {
    post.mockResolvedValueOnce({ data: { id: "job-1" } });
    await createJobFromAppointment({ appointment_id: "appointment-1", priority: "urgent" });
    expect(post).toHaveBeenCalledWith("/api/v1/jobs/from-appointment", { appointment_id: "appointment-1", priority: "urgent" });
    get.mockResolvedValueOnce({ data: { items: [], page: 1, page_size: 1, total_count: 0, total_pages: 0 } });
    await listJobs({ appointmentId: "appointment-1", page: 1, pageSize: 1 });
    expect(get).toHaveBeenCalledWith("/api/v1/jobs", { params: expect.objectContaining({ appointment_id: "appointment-1" }) });
  });
});
