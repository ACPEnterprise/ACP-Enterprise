import { ApiClient } from "../src/api/client";
import { ApiFailure, recoveryFor } from "../src/api/types";
import { SessionRepository } from "../src/auth/sessionRepository";
import type { Session } from "../src/auth/types";
import { readEnvironment } from "../src/config/environment";
import { activationTokenFromLink, isActivationLink } from "../src/linking/linking";
import { can, capabilitiesFromPermissions } from "../src/permissions/capabilities";
import type { ProtectedStorage } from "../src/storage/secureStorage";
import { createTimekeepingService } from "../src/api/timekeeping";

const session: Session = { user: { id: "synthetic-user", display_name: "Test Employee", normalized_email: "test@example.invalid" }, session_id: "synthetic-session", access_token: "secret-access", refresh_token: "secret-refresh", access_token_expires_at: "2099-01-01T00:00:00Z", refresh_token_expires_at: "2099-01-02T00:00:00Z" };
function memoryStorage(): ProtectedStorage & { values: Map<string, string> } { const values = new Map<string, string>(); return { values, get: async (key) => values.get(key) ?? null, set: async (key, value) => { values.set(key, value); }, remove: async (key) => { values.delete(key); } }; }

describe("employee app foundation", () => {
  it("uses protected session abstraction and logout clears it", async () => { const storage = memoryStorage(); const repo = new SessionRepository(storage); await repo.save(session); expect(await repo.load()).toEqual(session); await repo.clear(); expect(await repo.load()).toBeNull(); });
  it("clears stale malformed sessions", async () => { const storage = memoryStorage(); storage.values.set("acp.employee.session.v1", "{}"); expect(await new SessionRepository(storage).load()).toBeNull(); expect(storage.values.size).toBe(0); });
  it("represents permission-gated navigation", () => { expect(can(["home.view"], "time.self.view")).toBe(false); expect(can(["time.self.view"], "time.self.view")).toBe(true); });
  it("maps only the narrow own-day permission to My Day", () => { expect(capabilitiesFromPermissions(["COMPANY_EMPLOYEE_OPERATIONS_OWN_DAY_READ"])).toContain("my_day.view"); expect(capabilitiesFromPermissions(["COMPANY_DISPATCH_READ"])).not.toContain("my_day.view"); });
  it("recognizes activation links without retaining their secret", () => { expect(isActivationLink("https://employee.acpenterprise.com/activate?token=secret")).toBe(true); expect(isActivationLink("https://employee.acpenterprise.com/home")).toBe(false); });
  it("extracts activation references only from the accepted host and exact path", () => { expect(activationTokenFromLink("https://employee.acpenterprise.com/activate?token=opaque-reference")).toBe("opaque-reference"); expect(activationTokenFromLink("https://evil.example/activate?token=opaque-reference")).toBeNull(); expect(activationTokenFromLink("https://employee.acpenterprise.com/activate/other?token=opaque-reference")).toBeNull(); expect(activationTokenFromLink("acpemployee://activate?token=opaque-reference")).toBe("opaque-reference"); });
  it("fails closed for inactive production configuration", () => { expect(() => readEnvironment({ environment: "production", apiBaseUrl: "https://production-api.example.invalid", compatibilityVersion: "v1" })).toThrow(); });
  it("pins Preview configuration to the authorized ACP endpoint", () => {
    expect(readEnvironment({ environment: "preview", apiBaseUrl: "https://preview.allcountyhomeservices.com", compatibilityVersion: "v1" }).apiBaseUrl).toBe("https://preview.allcountyhomeservices.com");
    expect(() => readEnvironment({ environment: "preview", apiBaseUrl: "https://other.example.com", compatibilityVersion: "v1" })).toThrow();
  });
  it("requires an explicit activation flag even for a valid production URL", () => { expect(() => readEnvironment({ environment: "production", apiBaseUrl: "https://api.acpenterprise.com", compatibilityVersion: "v1", productionActivated: false })).toThrow("Production is inactive"); });
  it("accepts explicit development configuration", () => { expect(readEnvironment({ environment: "development", apiBaseUrl: "http://localhost:8000", compatibilityVersion: "v1" }).environment).toBe("development"); });
});

describe("central API client", () => {
  const logger = { info: jest.fn(), error: jest.fn() };
  beforeEach(() => { jest.restoreAllMocks(); logger.error.mockClear(); });
  it("returns explicit offline state and performs no request", async () => { const fetchSpy = jest.spyOn(global, "fetch"); const client = new ApiClient("http://localhost:8000", new SessionRepository(memoryStorage()), { isConnected: async () => false, subscribe: () => () => undefined }, logger, jest.fn()); await expect(client.request("/api/v1/test", { safeParse: jest.fn() } as never)).rejects.toMatchObject({ kind: "offline" }); expect(fetchSpy).not.toHaveBeenCalled(); });
  it("clears an unauthorized session and expires safely", async () => { const repo = new SessionRepository(memoryStorage()); await repo.save(session); jest.spyOn(global, "fetch").mockResolvedValue(new Response("{}", { status: 401 })); const expired = jest.fn(); const client = new ApiClient("http://localhost:8000", repo, { isConnected: async () => true, subscribe: () => () => undefined }, logger, expired); await expect(client.request("/api/v1/test", { safeParse: jest.fn() } as never)).rejects.toMatchObject({ kind: "unauthenticated" }); expect(await repo.load()).toBeNull(); expect(expired).toHaveBeenCalled(); });
  it("does not fabricate success for denial or server failure", async () => { for (const [status, kind] of [[403, "forbidden"], [503, "unavailable"]] as const) { jest.spyOn(global, "fetch").mockResolvedValueOnce(new Response("{}", { status })); const client = new ApiClient("http://localhost:8000", new SessionRepository(memoryStorage()), { isConnected: async () => true, subscribe: () => () => undefined }, logger, jest.fn()); await expect(client.request("/api/v1/test", { safeParse: jest.fn() } as never)).rejects.toMatchObject({ kind }); } });
  it("propagates safe request correlation and recovery vocabulary", async () => { jest.spyOn(global, "fetch").mockResolvedValue(new Response("{}", { status: 503, headers: { "X-Request-ID": "10000000-0000-4000-8000-000000000001" } })); const client = new ApiClient("http://localhost:8000", new SessionRepository(memoryStorage()), { isConnected: async () => true, subscribe: () => () => undefined }, logger, jest.fn()); await expect(client.request("/api/v1/test", { safeParse: jest.fn() } as never)).rejects.toMatchObject({ kind: "unavailable", correlationId: "10000000-0000-4000-8000-000000000001", recovery: "TEMPORARILY_UNAVAILABLE" }); expect(recoveryFor("conflict")).toBe("RETRY_AFTER_REFRESH"); expect(new ApiFailure("forbidden", "safe").recovery).toBe("OWNER_ADMIN_ACTION_REQUIRED"); });
  it("honors the accepted server recovery classification without exposing its body", async () => { jest.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail: { code: "validation", message: "safe", recovery: "USER_CORRECTION_REQUIRED", correlation_id: null } }), { status: 422, headers: { "content-type": "application/json" } })); const client = new ApiClient("http://localhost:8000", new SessionRepository(memoryStorage()), { isConnected: async () => true, subscribe: () => () => undefined }, logger, jest.fn()); await expect(client.request("/api/v1/test", { safeParse: jest.fn() } as never)).rejects.toMatchObject({ kind: "invalid_request", recovery: "USER_CORRECTION_REQUIRED" }); });
});

describe("authoritative punch contract", () => {
  it("sends only action and idempotency identity, never employee or client time", async () => {
    const request = jest.fn(async (...args: unknown[]) => { void args; return { punch_id: "synthetic", action: "clock_in", occurred_at: "2026-08-28T12:00:00Z", state: { state: "clocked_in", last_action: "clock_in", occurred_at: "2026-08-28T12:00:00Z", server_observed_at: "2026-08-28T12:00:01Z", elapsed_seconds: 1 }, completed_entry: null }; });
    await createTimekeepingService({ request } as never).punch("clock_in", "opaque-key");
    const [path, , init] = request.mock.calls[0]! as [string, unknown, { headers: Record<string, string>; body: string }];
    expect(path).toBe("/api/v1/timekeeping/me/punches");
    expect(init.headers).toEqual({ "Idempotency-Key": "opaque-key" });
    expect(JSON.parse(init.body)).toEqual({ action: "clock_in" });
  });
});
