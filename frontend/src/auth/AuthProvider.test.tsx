import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as authenticationApi from "../api/auth";
import * as authorizationApi from "../api/authorization";
import { AuthProvider } from "./AuthProvider";
import { useAuth } from "./useAuth";
import type { AuthenticationResult } from "./types";

vi.mock("../api/auth", () => ({
  login: vi.fn(),
  refreshSession: vi.fn(),
  logout: vi.fn(),
  logoutAll: vi.fn(),
}));
vi.mock("../api/authorization", () => ({ listAccessibleCompanies: vi.fn(), getEffectiveAuthorization: vi.fn() }));

const company = {
  id: "company-1",
  code: "ACP",
  name: "ACP Company",
  membership_id: "membership-1",
  default_branch_id: null,
  has_all_branch_access: true,
  branches: [],
};

const result: AuthenticationResult = {
  token_type: "bearer",
  user: {
    id: "user-1",
    normalized_email: "admin@example.com",
    first_name: "Preview",
    last_name: "Administrator",
    display_name: "Preview Administrator",
    email_verified_at: null,
  },
  session_id: "session-1",
  access_token: "access-token",
  refresh_token: "rotated-refresh-token",
  access_token_expires_at: "2026-07-20T21:00:00Z",
  refresh_token_expires_at: "2026-07-27T20:00:00Z",
  session_absolute_expires_at: "2026-07-21T20:00:00Z",
  session_idle_expires_at: "2026-07-20T22:00:00Z",
};

function Harness() {
  const { signIn, signOut, status, user } = useAuth();
  return (
    <div>
      <span>{status}</span>
      <span>{user?.display_name}</span>
      <button type="button" onClick={() => void signIn({ email: "admin@example.com", password: "password" })}>Sign in</button>
      <button type="button" onClick={() => void signOut()}>Sign out</button>
    </div>
  );
}

describe("AuthProvider", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    vi.mocked(authenticationApi.login).mockReset();
    vi.mocked(authenticationApi.refreshSession).mockReset();
    vi.mocked(authenticationApi.logout).mockReset();
    vi.mocked(authorizationApi.listAccessibleCompanies).mockReset();
    vi.mocked(authorizationApi.listAccessibleCompanies).mockResolvedValue([company]);
    vi.mocked(authorizationApi.getEffectiveAuthorization).mockResolvedValue({ permission_codes: [] });
  });

  it("restores a session by rotating the session-scoped refresh token", async () => {
    window.sessionStorage.setItem("acp.auth.refresh-token", "stored-refresh-token");
    vi.mocked(authenticationApi.refreshSession).mockResolvedValue(result);
    render(<AuthProvider><Harness /></AuthProvider>);
    expect(await screen.findByText("Preview Administrator")).toBeInTheDocument();
    expect(authenticationApi.refreshSession).toHaveBeenCalledWith("stored-refresh-token");
    expect(window.sessionStorage.getItem("acp.auth.refresh-token")).toBe("rotated-refresh-token");
  });

  it("signs in and keeps credentials out of browser storage", async () => {
    vi.mocked(authenticationApi.login).mockResolvedValue(result);
    render(<AuthProvider><Harness /></AuthProvider>);
    await screen.findByText("unauthenticated");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Preview Administrator")).toBeInTheDocument();
    expect(authenticationApi.login).toHaveBeenCalledWith({ email: "admin@example.com", password: "password" });
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.getItem("acp.auth.refresh-token")).toBe("rotated-refresh-token");
  });

  it("clears authentication after logout", async () => {
    window.sessionStorage.setItem("acp.auth.refresh-token", "stored-refresh-token");
    vi.mocked(authenticationApi.refreshSession).mockResolvedValue(result);
    vi.mocked(authenticationApi.logout).mockResolvedValue();
    render(<AuthProvider><Harness /></AuthProvider>);
    await screen.findByText("Preview Administrator");
    await act(async () => userEvent.click(screen.getByRole("button", { name: "Sign out" })));
    await waitFor(() => expect(screen.getByText("unauthenticated")).toBeInTheDocument());
    expect(window.sessionStorage.getItem("acp.auth.refresh-token")).toBeNull();
  });

  it("fails closed when restoration cannot rotate the token", async () => {
    window.sessionStorage.setItem("acp.auth.refresh-token", "expired-refresh-token");
    vi.mocked(authenticationApi.refreshSession).mockRejectedValue(new Error("expired"));
    render(<AuthProvider><Harness /></AuthProvider>);
    expect(await screen.findByText("unauthenticated")).toBeInTheDocument();
    expect(window.sessionStorage.getItem("acp.auth.refresh-token")).toBeNull();
  });
});
