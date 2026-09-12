import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
});
