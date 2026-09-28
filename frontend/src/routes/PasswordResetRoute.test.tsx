import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, AxiosHeaders } from "axios";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../api/client";
import { PasswordResetRoute } from "./PasswordResetRoute";

describe("PasswordResetRoute", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("requests recovery with a generic result", async () => {
    const request = vi.spyOn(apiClient, "post").mockResolvedValue({ data: {} });
    render(<MemoryRouter><PasswordResetRoute /></MemoryRouter>);
    await userEvent.type(screen.getByLabelText(/Email address/), "employee@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Send reset instructions" }));
    expect(request).toHaveBeenCalledWith("/api/v1/auth/password-reset/request", { email: "employee@example.com" });
    expect(await screen.findByText("If the account is eligible, recovery instructions will be sent.")).toBeInTheDocument();
  });

  it("consumes a token without rendering it", async () => {
    const request = vi.spyOn(apiClient, "post").mockResolvedValue({ data: {} });
    render(<MemoryRouter initialEntries={["/reset-password?token=private-reset-token"]}><PasswordResetRoute /></MemoryRouter>);
    expect(screen.queryByText("private-reset-token")).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/^New password/), "qualified-password");
    await userEvent.type(screen.getByLabelText(/^Confirm new password/), "qualified-password");
    await userEvent.click(screen.getByRole("button", { name: "Reset password" }));
    expect(request).toHaveBeenCalledWith("/api/v1/auth/password-reset/confirm", {
      token: "private-reset-token",
      new_password: "qualified-password",
    });
    expect(await screen.findByText(/Your password was reset/)).toBeInTheDocument();
  });

  it("does not validate or consume the token during passive page visits", () => {
    const request = vi.spyOn(apiClient, "post");
    const scannerVisit = render(<MemoryRouter initialEntries={["/reset-password?token=private-reset-token"]}><PasswordResetRoute /></MemoryRouter>);
    expect(screen.getByRole("button", { name: "Reset password" })).toBeEnabled();
    expect(request).not.toHaveBeenCalled();
    scannerVisit.unmount();

    render(<MemoryRouter initialEntries={["/reset-password?token=private-reset-token"]}><PasswordResetRoute /></MemoryRouter>);
    expect(screen.getByRole("button", { name: "Reset password" })).toBeEnabled();
    expect(request).not.toHaveBeenCalled();
  });

  it("keeps a valid reset token retryable after password-policy rejection", async () => {
    const policyFailure = new AxiosError(
      "validation",
      "ERR_BAD_REQUEST",
      undefined,
      undefined,
      { status: 422, statusText: "Unprocessable Entity", headers: {}, config: { headers: new AxiosHeaders() }, data: {} },
    );
    const request = vi.spyOn(apiClient, "post")
      .mockRejectedValueOnce(policyFailure)
      .mockResolvedValueOnce({ data: {} });
    render(<MemoryRouter initialEntries={["/reset-password?token=private-reset-token"]}><PasswordResetRoute /></MemoryRouter>);
    await userEvent.type(screen.getByLabelText(/^New password/), "qualified-password");
    await userEvent.type(screen.getByLabelText(/^Confirm new password/), "qualified-password");
    await userEvent.click(screen.getByRole("button", { name: "Reset password" }));
    expect(await screen.findByText(/reset link is still available/i)).toBeInTheDocument();

    await userEvent.clear(screen.getByLabelText(/^New password/));
    await userEvent.clear(screen.getByLabelText(/^Confirm new password/));
    await userEvent.type(screen.getByLabelText(/^New password/), "replacement-qualified-password");
    await userEvent.type(screen.getByLabelText(/^Confirm new password/), "replacement-qualified-password");
    await userEvent.click(screen.getByRole("button", { name: "Reset password" }));
    expect(await screen.findByText(/Your password was reset/)).toBeInTheDocument();
    expect(request).toHaveBeenCalledTimes(2);
  });

  it("does not misclassify an internal failure as an expired token", async () => {
    const internalFailure = new AxiosError(
      "internal",
      "ERR_BAD_RESPONSE",
      undefined,
      undefined,
      { status: 503, statusText: "Unavailable", headers: {}, config: { headers: new AxiosHeaders() }, data: {} },
    );
    vi.spyOn(apiClient, "post").mockRejectedValue(internalFailure);
    render(<MemoryRouter initialEntries={["/reset-password?token=private-reset-token"]}><PasswordResetRoute /></MemoryRouter>);
    await userEvent.type(screen.getByLabelText(/^New password/), "qualified-password");
    await userEvent.type(screen.getByLabelText(/^Confirm new password/), "qualified-password");
    await userEvent.click(screen.getByRole("button", { name: "Reset password" }));
    expect(await screen.findByText(/could not be completed right now/i)).toBeInTheDocument();
    expect(screen.queryByText(/expired, already used/i)).not.toBeInTheDocument();
  });
});
