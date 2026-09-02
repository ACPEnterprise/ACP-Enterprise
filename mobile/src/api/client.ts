import { z } from "zod";
import * as Crypto from "expo-crypto";
import type { SafeLogger } from "../diagnostics/safeLogger";
import type { NetworkMonitor } from "../network/networkMonitor";
import type { SessionRepository } from "../auth/sessionRepository";
import { ApiFailure } from "./types";
import { currentAppVersion } from "../diagnostics/buildIdentity";

export type ApiRequestOptions = RequestInit & {
  authentication?: "required" | "none";
  unauthorized?: "expire" | "preserve";
  conflict?: "conflict" | "invitation_invalid";
};
const recoverySchema = z.enum(["RETRY_SAFE", "RETRY_AFTER_REFRESH", "USER_CORRECTION_REQUIRED", "OWNER_ADMIN_ACTION_REQUIRED", "RECONCILIATION_REQUIRED", "TEMPORARILY_UNAVAILABLE", "TERMINAL_FAILURE"]);
async function serverRecovery(response: Response) { try { const body = await response.clone().json() as { detail?: { recovery?: unknown } }; return recoverySchema.safeParse(body.detail?.recovery).data; } catch { return undefined; } }

export class ApiClient {
  private companyId: string | null = null;
  private branchId: string | null = null;
  constructor(private readonly baseUrl: string, private readonly sessions: SessionRepository, private readonly network: NetworkMonitor, private readonly logger: SafeLogger, private readonly onExpired: () => void) {}
  setTenantContext(companyId: string, branchId: string | null) { this.companyId = companyId; this.branchId = branchId; }
  clearTenantContext() { this.companyId = null; this.branchId = null; }
  private async fetchResponse(path: string, options: ApiRequestOptions = {}): Promise<Response> {
    if (!(await this.network.isConnected())) throw new ApiFailure("offline", "Network unavailable");
    const { authentication = "required", unauthorized = "expire", conflict = "conflict", ...init } = options;
    const session = authentication === "required" ? await this.sessions.load() : null;
    const controller = new AbortController();
    const requestId = Crypto.randomUUID();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(new URL(path, this.baseUrl), { ...init, signal: controller.signal, headers: { Accept: "application/json", "Content-Type": "application/json", "X-ACP-Mobile-Version": currentAppVersion(), "X-Request-ID": requestId, ...(session ? { Authorization: `Bearer ${session.access_token}` } : {}), ...(authentication === "required" && this.companyId ? { "X-Company-ID": this.companyId } : {}), ...(authentication === "required" && this.branchId ? { "X-Branch-ID": this.branchId } : {}), ...init.headers } });
      const correlationId = response.headers.get("X-Request-ID") ?? requestId;
      const recovery = response.ok ? undefined : await serverRecovery(response);
      if (response.status === 401) {
        if (authentication === "none") throw new ApiFailure("invalid_credentials", "Authentication was rejected");
        if (unauthorized === "expire") { await this.sessions.clear(); this.clearTenantContext(); this.onExpired(); }
        throw new ApiFailure("unauthenticated", "Session expired", correlationId, recovery);
      }
      if (response.status === 403) throw new ApiFailure("forbidden", "Permission denied", correlationId, recovery);
      if (response.status === 404) throw new ApiFailure("not_found", "Assigned resource is no longer available", correlationId, recovery);
      if (response.status === 409) throw new ApiFailure(conflict, conflict === "invitation_invalid" ? "Invitation is not available" : "Authoritative state changed", correlationId, recovery);
      if (response.status === 422) throw new ApiFailure(recovery === "USER_CORRECTION_REQUIRED" ? "invalid_request" : "not_ready", recovery === "USER_CORRECTION_REQUIRED" ? "Request requires correction" : "Employee service is not ready", correlationId, recovery);
      if (response.status === 429) throw new ApiFailure("rate_limited", "Too many requests", correlationId, recovery);
      if (!response.ok) { this.logger.error("ACP API request failed", { path, status: response.status, correlationId, recovery }); throw new ApiFailure("unavailable", "Server unavailable", correlationId, recovery); }
      return response;
    } catch (error) {
      if (error instanceof ApiFailure) throw error;
      if (error instanceof Error && error.name === "AbortError") throw new ApiFailure("timeout", "Request timed out");
      throw new ApiFailure("unavailable", "Server unavailable");
    } finally { clearTimeout(timer); }
  }
  async request<T>(path: string, schema: z.ZodType<T>, options: ApiRequestOptions = {}): Promise<T> {
    const response = await this.fetchResponse(path, options);
    try {
      const result = schema.safeParse(await response.json());
      if (!result.success) throw new ApiFailure("malformed_response", "Malformed server response");
      return result.data;
    } catch (error) {
      if (error instanceof ApiFailure) throw error;
      throw new ApiFailure("malformed_response", "Malformed server response");
    }
  }
  async requestText(path: string, options: ApiRequestOptions = {}): Promise<{ content: string; contentType: string }> {
    const response = await this.fetchResponse(path, { ...options, headers: { Accept: "text/html", ...options.headers } });
    const contentType = response.headers.get("content-type")?.split(";", 1)[0] ?? "";
    if (contentType !== "text/html") throw new ApiFailure("malformed_response", "Unexpected protected artifact type");
    return { content: await response.text(), contentType };
  }
}
