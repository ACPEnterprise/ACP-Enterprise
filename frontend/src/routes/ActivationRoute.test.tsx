import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../api/client";
import { ActivationRoute } from "./ActivationRoute";

describe("ActivationRoute", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("completes activation without rendering the invitation token", async () => {
    const request = vi.spyOn(apiClient, "post").mockResolvedValue({ data: { status: "active" } });
    render(<MemoryRouter initialEntries={["/activate?token=private-invitation-token"]}><ActivationRoute /></MemoryRouter>);

    expect(screen.queryByText("private-invitation-token")).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/New password/), "qualified-password");
    await userEvent.type(screen.getByLabelText(/Confirm new password/), "qualified-password");
    await userEvent.click(screen.getByRole("button", { name: "Activate account" }));

    expect(request).toHaveBeenCalledWith("/api/v1/identity-onboarding/activate/complete", {
      token: "private-invitation-token",
      password: "qualified-password",
    });
    expect(await screen.findByText("Your account is activated. You can now sign in.")).toBeInTheDocument();
  });

  it("rejects mismatched passwords before calling the API", async () => {
    const request = vi.spyOn(apiClient, "post");
    render(<MemoryRouter initialEntries={["/activate?token=private-invitation-token"]}><ActivationRoute /></MemoryRouter>);
    await userEvent.type(screen.getByLabelText(/New password/), "qualified-password");
    await userEvent.type(screen.getByLabelText(/Confirm new password/), "different-password");
    await userEvent.click(screen.getByRole("button", { name: "Activate account" }));
    expect(await screen.findByText("Passwords do not match.")).toBeInTheDocument();
    expect(request).not.toHaveBeenCalled();
  });
});
