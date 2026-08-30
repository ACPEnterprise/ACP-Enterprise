import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { useFieldJobState } from "../../hooks/useTechnicianField";
import { JobCompletionStatus } from "./JobCompletionStatus";

vi.mock("../../hooks/useTechnicianField");

describe("JobCompletionStatus", () => {
  it("shows blockers and preserves domain ownership", () => {
    vi.mocked(useFieldJobState).mockReturnValue({ isPending: false, isError: false, data: { completion_ready: false, commercial_authorization: "missing", invoice_handoff_status: null, missing_requirements: ["work_summary"], invoice_id: null } } as never);
    render(<MemoryRouter><JobCompletionStatus jobId="job-1" /></MemoryRouter>);
    expect(screen.getByText("Blocked")).toBeVisible();
    expect(screen.getByText("work summary")).toBeVisible();
    expect(screen.getByText(/view is read-only/)).toBeVisible();
  });

  it("links an explicitly identified Invoice", () => {
    vi.mocked(useFieldJobState).mockReturnValue({ isPending: false, isError: false, data: { completion_ready: true, commercial_authorization: "accepted_estimate", invoice_handoff_status: "completed", missing_requirements: [], invoice_id: "invoice-1" } } as never);
    render(<MemoryRouter><JobCompletionStatus jobId="job-1" /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "Open authoritative Invoice" })).toHaveAttribute("href", "/invoices/invoice-1");
  });
});
