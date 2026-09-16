import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import type { Estimate } from "../../types/estimates";
import { EstimateDecisionControls } from "./EstimateDecisionControls";

const estimate = {
  id: "estimate-1",
  branch_id: "branch-1",
  status: "sent",
  version: 3,
  current_revision: {
    proposal_title: "Proposal",
    customer_message: null,
    terms: null,
    expires_at: null,
    lines: [],
  },
} as unknown as Estimate;
const mutations = (decisionError: unknown = null) => ({
  transition: {
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  },
  decide: {
    mutate: vi.fn(),
    isPending: false,
    isError: Boolean(decisionError),
    error: decisionError,
  },
  convert: {
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    data: null,
  },
  revise: {
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  },
});

describe("EstimateDecisionControls", () => {
  it("creates an immutable presentation revision from sealed lines", () => {
    const controls = mutations();
    render(
      <EstimateDecisionControls
        estimate={{
          ...estimate,
          customer_id: "customer-1",
          service_location_id: "location-1",
          current_revision: {
            proposal_title: "Original proposal",
            customer_message: "Original message",
            terms: "Original terms",
            expires_at: null,
            lines: [
              {
                snapshot_id: "snapshot-1",
                title: "Drain service",
                description: "Clear the drain",
              },
            ],
          },
        } as Estimate}
        mutations={controls as never}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Revise customer presentation" }));
    fireEvent.change(screen.getByLabelText("Proposal title"), {
      target: { value: "Updated proposal" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create revised Draft" }));

    expect(controls.revise.mutate).toHaveBeenCalledWith({
      id: "estimate-1",
      input: expect.objectContaining({
        expected_version: 3,
        proposal_title: "Updated proposal",
        lines: [
          {
            snapshot_id: "snapshot-1",
            title: "Drain service",
            description: "Clear the drain",
          },
        ],
      }),
    });
  });

  it("shows persistent Job lineage and does not offer duplicate conversion", () => {
    const controls = mutations();
    render(
      <MemoryRouter>
        <EstimateDecisionControls
          estimate={{
            ...estimate,
            status: "approved",
            service_location_id: "location-1",
            conversion: {
              id: "conversion-1",
              estimate_id: "estimate-1",
              estimate_revision_id: "revision-1",
              job_id: "job-1",
              job_number: "JOB-000001",
              snapshot_lineage_digest: "a".repeat(64),
              converted_at: "2026-09-16T12:00:00Z",
            },
          } as Estimate}
          mutations={controls as never}
        />
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "JOB-000001" })).toHaveAttribute(
      "href",
      "/jobs/job-1",
    );
    expect(
      screen.queryByRole("button", { name: "Convert approved Estimate to Job" }),
    ).not.toBeInTheDocument();
  });

  it("binds a viewed transition to current branch and version", () => {
    const controls = mutations();
    render(
      <EstimateDecisionControls
        estimate={estimate}
        mutations={controls as never}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Record customer view" }),
    );
    expect(controls.transition.mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        id: "estimate-1",
        action: "view",
        input: expect.objectContaining({
          branch_id: "branch-1",
          expected_version: 3,
        }),
      }),
    );
  });

  it("converts only an approved Estimate with a replay-safe identity", () => {
    const controls = mutations();
    render(
      <EstimateDecisionControls
        estimate={{ ...estimate, status: "approved", service_location_id: "location-1" }}
        mutations={controls as never}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Convert approved Estimate to Job" }),
    );
    expect(controls.convert.mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        id: "estimate-1",
        input: expect.objectContaining({
          branch_id: "branch-1",
          expected_version: 3,
          idempotency_key: "estimate-job-estimate-1",
        }),
      }),
    );
  });

  it("explains and blocks Job conversion when Service Location is missing", () => {
    const controls = mutations();
    render(
      <EstimateDecisionControls
        estimate={{ ...estimate, status: "approved", service_location_id: null }}
        mutations={controls as never}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(/select a service location/i);
    expect(
      screen.getByRole("button", { name: "Convert approved Estimate to Job" }),
    ).toBeDisabled();
  });

  it("requires explicit Customer evidence for rejection", () => {
    const controls = mutations();
    render(
      <EstimateDecisionControls
        estimate={estimate}
        mutations={controls as never}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Record rejection" }));
    fireEvent.change(screen.getByLabelText("Customer name"), {
      target: { value: "Alex Customer" },
    });
    fireEvent.change(screen.getByLabelText("Rejection reason"), {
      target: { value: "Scope declined" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirm rejection" }));
    expect(controls.decide.mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        action: "reject",
        input: expect.objectContaining({
          customer_name: "Alex Customer",
          rejection_reason: "Scope declined",
        }),
      }),
    );
    expect(screen.getByText(/do not send communications/)).toBeVisible();
  });

  it("announces governed recovery without reflecting backend details", () => {
    const controls = mutations({
      isAxiosError: true,
      response: {
        data: {
          detail: {
            recovery: "RETRY_AFTER_REFRESH",
            message: "sql-provider-secret-canary",
          },
        },
      },
    });
    render(
      <EstimateDecisionControls
        estimate={estimate}
        mutations={controls as never}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(/authority changed/i);
    expect(
      screen.queryByText(/sql-provider-secret-canary/),
    ).not.toBeInTheDocument();
  });
});
