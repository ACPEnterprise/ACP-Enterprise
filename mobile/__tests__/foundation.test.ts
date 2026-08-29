import { ApiClient } from "../src/api/client";
import { SessionRepository } from "../src/auth/sessionRepository";
import type { Session } from "../src/auth/types";
import { readEnvironment } from "../src/config/environment";
import { isActivationLink } from "../src/linking/linking";
import { can } from "../src/permissions/capabilities";
import type { ProtectedStorage } from "../src/storage/secureStorage";

const session: Session = { user: { id: "synthetic-user", display_name: "Test Employee", normalized_email: "test@example.invalid" }, session_id: "synthetic-session", access_token: "secret-access", refresh_token: "secret-refresh", access_token_expires_at: "2099-01-01T00:00:00Z", refresh_token_expires_at: "2099-01-02T00:00:00Z" };
function memoryStorage(): ProtectedStorage & { values: Map<string, string> } { const values = new Map<string, string>(); return { values, get: async (key) => values.get(key) ?? null, set: async (key, value) => { values.set(key, value); }, remove: async (key) => { values.delete(key); } }; }

describe("employee app foundation", () => {
  it("uses protected session abstraction and logout clears it", async () => { const storage = memoryStorage(); const repo = new SessionRepository(storage); await repo.save(session); expect(await repo.load()).toEqual(session); await repo.clear(); expect(await repo.load()).toBeNull(); });
  it("clears stale malformed sessions", async () => { const storage = memoryStorage(); storage.values.set("acp.employee.session.v1", "{}"); expect(await new SessionRepository(storage).load()).toBeNull(); expect(storage.values.size).toBe(0); });
  it("represents permission-gated navigation", () => { expect(can(["home.view"], "time.self.view")).toBe(false); expect(can(["time.self.view"], "time.self.view")).toBe(true); });
  it("recognizes activation links without retaining their secret", () => { expect(isActivationLink("https://employee.acpenterprise.com/activate?token=secret")).toBe(true); expect(isActivationLink("https://employee.acpenterprise.com/home")).toBe(false); });
  it("fails closed for inactive production configuration", () => { expect(() => readEnvironment({ environment: "production", apiBaseUrl: "https://production-api.example.invalid", compatibilityVersion: "v1" })).toThrow(); });
  it("accepts explicit development configuration", () => { expect(readEnvironment({ environment: "development", apiBaseUrl: "http://localhost:8000", compatibilityVersion: "v1" }).environment).toBe("development"); });
});

describe("central API client", () => {
  const logger = { info: jest.fn(), error: jest.fn() };
  beforeEach(() => { jest.restoreAllMocks(); logger.error.mockClear(); });
  it("returns explicit offline state and performs no request", async () => { const fetchSpy = jest.spyOn(global, "fetch"); const client = new ApiClient("http://localhost:8000", new SessionRepository(memoryStorage()), { isConnected: async () => false, subscribe: () => () => undefined }, logger, jest.fn()); await expect(client.request("/api/v1/test", { safeParse: jest.fn() } as never)).rejects.toMatchObject({ kind: "offline" }); expect(fetchSpy).not.toHaveBeenCalled(); });
  it("clears an unauthorized session and expires safely", async () => { const repo = new SessionRepository(memoryStorage()); await repo.save(session); jest.spyOn(global, "fetch").mockResolvedValue(new Response("{}", { status: 401 })); const expired = jest.fn(); const client = new ApiClient("http://localhost:8000", repo, { isConnected: async () => true, subscribe: () => () => undefined }, logger, expired); await expect(client.request("/api/v1/test", { safeParse: jest.fn() } as never)).rejects.toMatchObject({ kind: "unauthenticated" }); expect(await repo.load()).toBeNull(); expect(expired).toHaveBeenCalled(); });
  it("does not fabricate success for denial or server failure", async () => { for (const [status, kind] of [[403, "forbidden"], [503, "unavailable"]] as const) { jest.spyOn(global, "fetch").mockResolvedValueOnce(new Response("{}", { status })); const client = new ApiClient("http://localhost:8000", new SessionRepository(memoryStorage()), { isConnected: async () => true, subscribe: () => () => undefined }, logger, jest.fn()); await expect(client.request("/api/v1/test", { safeParse: jest.fn() } as never)).rejects.toMatchObject({ kind }); } });
});
