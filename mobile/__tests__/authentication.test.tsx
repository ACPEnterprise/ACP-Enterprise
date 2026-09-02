import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import { AuthenticationCoordinator } from "../src/auth/authenticationCoordinator";
import { SessionRepository } from "../src/auth/sessionRepository";
import type { Session } from "../src/auth/types";
import type { ProtectedStorage } from "../src/storage/secureStorage";
import { ApiFailure } from "../src/api/types";
import { ApiClient } from "../src/api/client";
import { completeActivation, login } from "../src/api/auth";
import { ActivationScreen } from "../src/screens/ActivationScreen";
import { RestrictedStateScreen } from "../src/screens/RestrictedStateScreen";
import { SignInScreen } from "../src/screens/SignInScreen";

const session: Session = { user: { id: "synthetic-user", display_name: "Synthetic Employee", normalized_email: "employee@example.invalid" }, session_id: "synthetic-session", access_token: "synthetic-access-token", refresh_token: "synthetic-refresh-token-value-long-enough", access_token_expires_at: "2099-01-01T00:00:00Z", refresh_token_expires_at: "2099-02-01T00:00:00Z" };
function storage(): ProtectedStorage & { values: Map<string, string> } { const values = new Map<string, string>(); return { values, get: async (key) => values.get(key) ?? null, set: async (key, value) => { values.set(key, value); }, remove: async (key) => { values.delete(key); } }; }
function api() {
  let contextFailures = 0;
  const request: jest.Mock = jest.fn(async (path: string) => {
    if (path === "/api/v1/auth/login" || path === "/api/v1/auth/refresh") return session;
    if (path === "/api/v1/auth/session") return { session_id: session.session_id, status: "active", absolute_expires_at: "2099-02-01T00:00:00Z", idle_expires_at: null };
    if (path === "/api/v1/authorization/companies") return [{ id: "synthetic-company", membership_id: "synthetic-membership", default_branch_id: "synthetic-branch", branches: [{ id: "synthetic-branch" }] }];
    if (path === "/api/v1/authorization/context") { if (contextFailures > 0) { contextFailures -= 1; throw new ApiFailure("forbidden", "stale authorization"); } return { company_id: "synthetic-company", active_branch_id: "synthetic-branch", permission_codes: ["COMPANY_TIMEKEEPING_OWN_READ"] }; }
    if (path === "/api/v1/auth/logout") return { message: "ok" };
    if (path === "/api/v1/identity-onboarding/activate/complete") return { status: "activated", masked_login: "e***@example.invalid" };
    throw new Error(`Unexpected synthetic path: ${path}`);
  });
  return { request, setTenantContext: jest.fn(), clearTenantContext: jest.fn(), failContextOnce() { contextFailures = 1; } };
}
function coordinator(initial?: Session) {
  const protectedStorage = storage(); const sessions = new SessionRepository(protectedStorage); const client = api(); const qualify = jest.fn(async () => undefined);
  const auth = new AuthenticationCoordinator(client as never, sessions, qualify);
  return { protectedStorage, sessions, client, qualify, auth, initialize: async () => { if (initial) await sessions.save(initial); } };
}

describe("authentication coordinator", () => {
  it("routes an unauthenticated restore to sign in", async () => { const h = coordinator(); expect(await h.auth.restore()).toEqual({ kind: "anonymous" }); });
  it("persists accepted session only in protected storage and reaches the authorized shell", async () => { const h = coordinator(); const result = await h.auth.signIn("employee@example.invalid", "not-persisted-password"); expect(result).toMatchObject({ kind: "authenticated" }); expect(await h.sessions.load()).toEqual(session); expect(JSON.stringify([...h.protectedStorage.values.values()])).not.toContain("not-persisted-password"); expect(h.qualify).toHaveBeenCalledWith(expect.arrayContaining(["time.self.view"])); });
  it("fails invalid credentials without persisting password or session", async () => { const h = coordinator(); h.client.request.mockRejectedValueOnce(new ApiFailure("invalid_credentials", "invalid")); await expect(h.auth.signIn("employee@example.invalid", "wrong-password")).rejects.toMatchObject({ kind: "invalid_credentials" }); expect(await h.sessions.load()).toBeNull(); expect(JSON.stringify([...h.protectedStorage.values.values()])).not.toContain("wrong-password"); });
  it("verifies a protected session before restoring authenticated state", async () => { const h = coordinator(session); await h.initialize(); expect(await h.auth.restore()).toMatchObject({ kind: "authenticated" }); expect(h.client.request.mock.calls[0]?.[0]).toBe("/api/v1/auth/session"); });
  it("rotates an expired session and handles authorization-version invalidation", async () => { const h = coordinator(session); await h.initialize(); h.client.request.mockRejectedValueOnce(new ApiFailure("unauthenticated", "expired")); expect(await h.auth.restore()).toMatchObject({ kind: "authenticated" }); expect(h.client.request.mock.calls.some((call) => call[0] === "/api/v1/auth/refresh")).toBe(true); h.client.failContextOnce(); expect(await h.auth.restore()).toMatchObject({ kind: "authenticated" }); expect(h.client.request.mock.calls.filter((call) => call[0] === "/api/v1/auth/refresh").length).toBeGreaterThanOrEqual(2); });
  it("returns offline verification safely without clearing a stored session", async () => { const h = coordinator(session); await h.initialize(); h.client.request.mockRejectedValueOnce(new ApiFailure("offline", "offline")); await expect(h.auth.restore()).rejects.toMatchObject({ kind: "offline" }); expect(await h.sessions.load()).toEqual(session); });
  it("clears protected state even when authoritative logout is unavailable", async () => { const h = coordinator(session); await h.initialize(); h.client.request.mockRejectedValueOnce(new ApiFailure("offline", "offline")); await h.auth.signOut(); expect(await h.sessions.load()).toBeNull(); expect(h.client.clearTenantContext).toHaveBeenCalled(); });
  it("returns setup-incomplete and access-limited without inferring identity", async () => { const noCompany = coordinator(session); await noCompany.initialize(); noCompany.client.request.mockImplementation(async (path: string) => path === "/api/v1/auth/session" ? { session_id: "s", status: "active", absolute_expires_at: "2099-01-01", idle_expires_at: null } : path === "/api/v1/authorization/companies" ? [] : null); expect(await noCompany.auth.restore()).toEqual({ kind: "onboarding_incomplete" }); const limited = coordinator(session); await limited.initialize(); limited.client.request.mockImplementation(async (path: string) => path === "/api/v1/auth/session" ? {} : path === "/api/v1/authorization/companies" ? [{ id: "c", membership_id: "m", default_branch_id: null, branches: [] }] : path === "/api/v1/authorization/context" ? { company_id: "c", active_branch_id: null, permission_codes: [] } : null); expect(await limited.auth.restore()).toEqual({ kind: "access_limited" }); });
});

describe("authoritative authentication transport", () => {
  afterEach(() => jest.restoreAllMocks());
  it("maps login rejection without expiring an unrelated session or logging identity", async () => { const protectedStorage = storage(); const sessions = new SessionRepository(protectedStorage); const expired = jest.fn(); const logger = { info: jest.fn(), error: jest.fn() }; const client = new ApiClient("https://api.example.invalid", sessions, { isConnected: async () => true, subscribe: () => () => undefined }, logger, expired); jest.spyOn(global, "fetch").mockResolvedValue(new Response("{}", { status: 401 })); await expect(login(client, "synthetic@example.invalid", "never-stored")).rejects.toMatchObject({ kind: "invalid_credentials" }); expect(expired).not.toHaveBeenCalled(); expect(JSON.stringify(logger)).not.toMatch(/synthetic@example|never-stored/); });
  it("collapses authoritative activation conflicts and sends no Employee identity", async () => { const client = new ApiClient("https://api.example.invalid", new SessionRepository(storage()), { isConnected: async () => true, subscribe: () => () => undefined }, { info: jest.fn(), error: jest.fn() }, jest.fn()); const fetchMock = jest.spyOn(global, "fetch").mockResolvedValue(new Response("{}", { status: 409 })); await expect(completeActivation(client, "opaque-invitation", "direct-password")).rejects.toMatchObject({ kind: "invitation_invalid" }); const request = fetchMock.mock.calls[0]?.[1]; expect(request?.body).toBe(JSON.stringify({ token: "opaque-invitation", password: "direct-password" })); expect(String(request?.body)).not.toMatch(/employee_id|membership_id|company_id/); });
});

describe("interactive sign in", () => {
  it("submits credentials, clears password input, and provides visibility/accessibility controls", async () => { const submit = jest.fn(async () => undefined); render(<SignInScreen onSignIn={submit} />); fireEvent.changeText(screen.getByLabelText("ACP login email"), "employee@example.invalid"); fireEvent.changeText(screen.getByLabelText("ACP account password"), "direct-password"); fireEvent.press(screen.getByLabelText("Show password")); fireEvent.press(screen.getByLabelText("Sign in to ACP Employee")); await waitFor(() => expect(submit).toHaveBeenCalledWith("employee@example.invalid", "direct-password")); expect(screen.getByLabelText("ACP account password").props.value).toBe(""); });
  it.each([["invalid_credentials", /incorrect/], ["offline", /offline/], ["unavailable", /temporarily unavailable/]] as const)("renders %s safely", async (kind, expected) => { const submit = jest.fn(async () => { throw new ApiFailure(kind, kind); }); render(<SignInScreen onSignIn={submit} />); fireEvent.changeText(screen.getByLabelText("ACP login email"), "synthetic@example.invalid"); fireEvent.changeText(screen.getByLabelText("ACP account password"), "wrong"); fireEvent.press(screen.getByLabelText("Sign in to ACP Employee")); expect(await screen.findByText(expected)).toBeOnTheScreen(); expect(screen.getByLabelText("ACP account password").props.value).toBe(""); });
});

describe("secure invitation activation", () => {
  it("establishes credential without retaining the invitation or password", async () => { const activate = jest.fn(async () => undefined); render(<ActivationScreen token="synthetic-invitation-secret" onActivate={activate} onComplete={jest.fn()} />); fireEvent.changeText(screen.getByLabelText("New ACP account password"), "direct-password"); fireEvent.changeText(screen.getByLabelText("Confirm new ACP account password"), "direct-password"); fireEvent.press(screen.getByText("Activate Account")); await waitFor(() => expect(activate).toHaveBeenCalledWith("synthetic-invitation-secret", "direct-password")); expect(await screen.findByText("Activation complete")).toBeOnTheScreen(); expect(screen.queryByText(/synthetic-invitation-secret|direct-password/)).not.toBeOnTheScreen(); });
  it.each(["expired", "revoked", "superseded", "consumed", "invalid"])("handles %s invitation with the accepted non-enumerating response", async () => { const activate = jest.fn(async () => { throw new ApiFailure("invitation_invalid", "hidden"); }); render(<ActivationScreen token={`synthetic-${Date.now()}`} onActivate={activate} onComplete={jest.fn()} />); fireEvent.changeText(screen.getByLabelText("New ACP account password"), "direct-password"); fireEvent.changeText(screen.getByLabelText("Confirm new ACP account password"), "direct-password"); fireEvent.press(screen.getByText("Activate Account")); expect(await screen.findByText(/no longer available/)).toBeOnTheScreen(); });
  it("rejects missing activation reference and does not submit", () => { const activate = jest.fn(); render(<ActivationScreen token={null} onActivate={activate} onComplete={jest.fn()} />); expect(screen.getByText(/activation link is invalid/i)).toBeOnTheScreen(); expect(screen.getByText("Activate Account")).toBeDisabled(); });
});

describe("restricted authenticated states", () => {
  it.each(["onboarding_incomplete", "access_limited"] as const)("renders %s with revalidation and logout", (kind) => { render(<RestrictedStateScreen kind={kind} onRetry={jest.fn()} onLogout={jest.fn()} />); expect(screen.getByText("Check Access Again")).toBeOnTheScreen(); expect(screen.getByText("Sign Out")).toBeOnTheScreen(); });
});
