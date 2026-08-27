import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import { addWorkNote, recordCustomerDisposition, transitionJob } from "./technicianField";

vi.mock("./client", () => ({ apiClient: { get: vi.fn(), post: vi.fn() } }));

describe("technician field API", () => {
  beforeEach(() => vi.clearAllMocks());

  it("records work evidence through the field boundary", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { completion_ready: false } });
    await addWorkNote("job-1", "Installed and tested fixture.");
    expect(apiClient.post).toHaveBeenCalledWith(
      "/api/v1/technician/jobs/job-1/notes",
      expect.objectContaining({ note_type: "work_performed", content: "Installed and tested fixture." }),
    );
  });

  it("separates approval evidence from exception dispositions", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { completion_ready: true } });
    await recordCustomerDisposition("job-1", "approved", "Pat Customer", "");
    expect(apiClient.post).toHaveBeenCalledWith(
      "/api/v1/technician/jobs/job-1/customer-approval",
      expect.objectContaining({ disposition: "approved", customer_name: "Pat Customer", reason: null }),
    );
  });

  it("uses the controlled pause reason", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: {} });
    await transitionJob("job-1", "pause", 3);
    expect(apiClient.post).toHaveBeenCalledWith(
      "/api/v1/jobs/job-1/pause",
      { expected_version: 3, reason_code: "operational_hold" },
    );
  });
});
