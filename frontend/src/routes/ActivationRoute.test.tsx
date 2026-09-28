import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AxiosError, AxiosHeaders } from "axios";

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

  it("does not validate or consume the token during passive page visits", () => {
    const request = vi.spyOn(apiClient, "post");
    const first = render(<MemoryRouter initialEntries={["/activate?token=private-invitation-token"]}><ActivationRoute /></MemoryRouter>);
    expect(screen.getByRole("button", { name: "Activate account" })).toBeEnabled();
    expect(request).not.toHaveBeenCalled();
    first.unmount();

    render(<MemoryRouter initialEntries={["/activate?token=private-invitation-token"]}><ActivationRoute /></MemoryRouter>);
    expect(screen.getByRole("button", { name: "Activate account" })).toBeEnabled();
    expect(request).not.toHaveBeenCalled();
  });

  it("keeps a valid link retryable after password-policy rejection", async () => {
    const policyFailure = new AxiosError(
      "validation",
      "ERR_BAD_REQUEST",
      undefined,
      undefined,
      { status: 422, statusText: "Unprocessable Entity", headers: {}, config: { headers: new AxiosHeaders() }, data: {} },
    );
    const request = vi.spyOn(apiClient, "post")
      .mockRejectedValueOnce(policyFailure)
      .mockResolvedValueOnce({ data: { status: "active" } });
    render(<MemoryRouter initialEntries={["/activate?token=private-invitation-token"]}><ActivationRoute /></MemoryRouter>);
    await userEvent.type(screen.getByLabelText(/New password/), "qualified-password");
    await userEvent.type(screen.getByLabelText(/Confirm new password/), "qualified-password");
    await userEvent.click(screen.getByRole("button", { name: "Activate account" }));
    expect(await screen.findByText(/activation link is still available/i)).toBeInTheDocument();

    await userEvent.clear(screen.getByLabelText(/New password/));
    await userEvent.clear(screen.getByLabelText(/Confirm new password/));
    await userEvent.type(screen.getByLabelText(/New password/), "replacement-qualified-password");
    await userEvent.type(screen.getByLabelText(/Confirm new password/), "replacement-qualified-password");
    await userEvent.click(screen.getByRole("button", { name: "Activate account" }));
    expect(await screen.findByText("Your account is activated. You can now sign in.")).toBeInTheDocument();
    expect(request).toHaveBeenCalledTimes(2);
  });
});
