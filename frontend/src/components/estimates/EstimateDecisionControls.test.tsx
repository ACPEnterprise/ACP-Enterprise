import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Estimate } from "../../types/estimates";
import { EstimateDecisionControls } from "./EstimateDecisionControls";

const estimate = { id: "estimate-1", branch_id: "branch-1", status: "sent", version: 3 } as Estimate;
const mutations = (decisionError: unknown = null) => ({
  transition: { mutate: vi.fn(), isPending: false, isError: false, error: null },
  decide: { mutate: vi.fn(), isPending: false, isError: Boolean(decisionError), error: decisionError },
});

describe("EstimateDecisionControls", () => {
  it("binds a viewed transition to current branch and version", () => {
    const controls = mutations();
    render(<EstimateDecisionControls estimate={estimate} mutations={controls as never} />);
    fireEvent.click(screen.getByRole("button", { name: "Record customer view" }));
    expect(controls.transition.mutate).toHaveBeenCalledWith(expect.objectContaining({ id: "estimate-1", action: "view", input: expect.objectContaining({ branch_id: "branch-1", expected_version: 3 }) }));
  });

  it("requires explicit Customer evidence for rejection", () => {
    const controls = mutations();
    render(<EstimateDecisionControls estimate={estimate} mutations={controls as never} />);
    fireEvent.click(screen.getByRole("button", { name: "Record rejection" }));
    fireEvent.change(screen.getByLabelText("Customer name"), { target: { value: "Alex Customer" } });
    fireEvent.change(screen.getByLabelText("Rejection reason"), { target: { value: "Scope declined" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm rejection" }));
    expect(controls.decide.mutate).toHaveBeenCalledWith(expect.objectContaining({ action: "reject", input: expect.objectContaining({ customer_name: "Alex Customer", rejection_reason: "Scope declined" }) }));
    expect(screen.getByText(/do not send communications/)).toBeVisible();
  });

  it("announces governed recovery without reflecting backend details", () => {
    const controls = mutations({
      isAxiosError: true,
      response: { data: { detail: { recovery: "RETRY_AFTER_REFRESH", message: "sql-provider-secret-canary" } } },
    });
    render(<EstimateDecisionControls estimate={estimate} mutations={controls as never} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/authority changed/i);
    expect(screen.queryByText(/sql-provider-secret-canary/)).not.toBeInTheDocument();
  });
});
