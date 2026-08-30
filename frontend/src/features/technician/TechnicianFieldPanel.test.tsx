import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useTechnicianField } from "../../hooks/useTechnicianField";
import { TechnicianFieldPanel } from "./TechnicianFieldPanel";

vi.mock("../../hooks/useTechnicianField");

const mutation = (error: unknown = null) => ({
  isPending: false,
  isError: Boolean(error),
  error,
  mutate: vi.fn(),
});

describe("TechnicianFieldPanel recovery", () => {
  it("announces structured recovery without reflecting backend details", () => {
    vi.mocked(useTechnicianField).mockReturnValue({
      state: {
        isLoading: false,
        isError: false,
        data: {
          work_summary_recorded: true,
          customer_disposition: "approved",
          completion_ready: false,
          missing_requirements: ["commercial_authorization"],
          commercial_authorization: "missing",
          invoice_handoff_status: null,
        },
      },
      note: mutation(),
      approval: mutation(),
      arrival: mutation(),
      lifecycle: mutation({
        isAxiosError: true,
        response: {
          data: {
            detail: {
              recovery: "RECONCILIATION_REQUIRED",
              message: "sql-provider-secret-canary",
            },
          },
        },
      }),
      handoff: mutation(),
    } as never);

    render(
      <TechnicianFieldPanel
        item={{
          appointment_id: "appointment-1",
          assignment_version: 1,
          job_id: "job-1",
          job_version: 2,
          job_status: "in_progress",
          arrival_state: "arrived",
        } as never}
      />,
    );

    expect(screen.getByRole("alert", { name: "Action not recorded" })).toHaveTextContent(
      /requires office reconciliation/i,
    );
    expect(screen.queryByText(/sql-provider-secret-canary/)).not.toBeInTheDocument();
  });
});
