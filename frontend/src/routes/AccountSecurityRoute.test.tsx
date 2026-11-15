import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../api/client";
import { useAuth } from "../auth";
import { AccountSecurityRoute } from "./AccountSecurityRoute";

vi.mock("../auth", () => ({ useAuth: vi.fn() }));

describe("AccountSecurityRoute", () => {
  const signOut = vi.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    vi.restoreAllMocks();
    signOut.mockClear();
    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: "user-1",
        normalized_email: "owner@example.com",
        first_name: "Owner",
        last_name: "Example",
        display_name: "Owner Example",
        email_verified_at: null,
      },
      signOut,
    } as unknown as ReturnType<typeof useAuth>);
  });

  it("shows the bound login identity and submits the three-field change", async () => {
    const request = vi.spyOn(apiClient, "post").mockResolvedValue({ data: {} });
    render(<MemoryRouter><AccountSecurityRoute /></MemoryRouter>);

    expect(screen.getByTestId("account-login-email")).toHaveTextContent("owner@example.com");
    await userEvent.type(screen.getByLabelText(/^Current password/), "current-password");
    await userEvent.type(screen.getByLabelText(/^New password/), "new-password-123");
    await userEvent.type(screen.getByLabelText(/^Confirm new password/), "new-password-123");
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));

    expect(request).toHaveBeenCalledWith("/api/v1/auth/password-change", {
      current_password: "current-password",
      new_password: "new-password-123",
      confirm_new_password: "new-password-123",
    });
    expect(signOut).toHaveBeenCalledOnce();
  });

  it("blocks mismatched confirmation without sending a password", async () => {
    const request = vi.spyOn(apiClient, "post").mockResolvedValue({ data: {} });
    render(<MemoryRouter><AccountSecurityRoute /></MemoryRouter>);

    await userEvent.type(screen.getByLabelText(/^Current password/), "current-password");
    await userEvent.type(screen.getByLabelText(/^New password/), "new-password-123");
    await userEvent.type(screen.getByLabelText(/^Confirm new password/), "different-password");
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));

    expect(await screen.findByText("New passwords do not match.")).toBeVisible();
    expect(request).not.toHaveBeenCalled();
    expect(signOut).not.toHaveBeenCalled();
  });
});
