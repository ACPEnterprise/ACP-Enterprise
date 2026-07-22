import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { JobsEmptyState, JobsErrorState, JobsLoadingState } from "./JobStates";

describe("Jobs request states", () => {
  it("announces loading and renders the empty state", () => {
    const { rerender } = render(<JobsLoadingState />);
    expect(screen.getByRole("status", { name: "Loading Jobs" })).toBeInTheDocument();
    rerender(<JobsEmptyState />);
    expect(screen.getByRole("heading", { name: "No Jobs found" })).toBeInTheDocument();
  });

  it("renders a safe retryable error", async () => {
    const retry = vi.fn();
    render(<JobsErrorState onRetry={retry} />);
    expect(screen.getByText(/request could not be completed/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledOnce();
  });
});
