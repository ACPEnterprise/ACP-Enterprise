import { z } from "zod";
import type { SafeLogger } from "../diagnostics/safeLogger";
import type { NetworkMonitor } from "../network/networkMonitor";
import type { SessionRepository } from "../auth/sessionRepository";
import { ApiFailure } from "./types";

export class ApiClient {
  constructor(private readonly baseUrl: string, private readonly sessions: SessionRepository, private readonly network: NetworkMonitor, private readonly logger: SafeLogger, private readonly onExpired: () => void) {}
  async request<T>(path: string, schema: z.ZodType<T>, init: RequestInit = {}): Promise<T> {
    if (!(await this.network.isConnected())) throw new ApiFailure("offline", "Network unavailable");
    const session = await this.sessions.load();
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(new URL(path, this.baseUrl), { ...init, signal: controller.signal, headers: { Accept: "application/json", "Content-Type": "application/json", "X-ACP-Mobile-Version": "0.1.0", ...(session ? { Authorization: `Bearer ${session.access_token}` } : {}), ...init.headers } });
      if (response.status === 401) { await this.sessions.clear(); this.onExpired(); throw new ApiFailure("unauthenticated", "Session expired"); }
      if (response.status === 403) throw new ApiFailure("forbidden", "Permission denied");
      if (response.status === 409) throw new ApiFailure("conflict", "Authoritative state changed");
      if (response.status === 422) throw new ApiFailure("not_ready", "Employee timekeeping is not ready");
      if (!response.ok) { this.logger.error("ACP API request failed", { path, status: response.status }); throw new ApiFailure("unavailable", "Server unavailable"); }
      const result = schema.safeParse(await response.json());
      if (!result.success) throw new ApiFailure("malformed_response", "Malformed server response");
      return result.data;
    } catch (error) {
      if (error instanceof ApiFailure) throw error;
      if (error instanceof Error && error.name === "AbortError") throw new ApiFailure("timeout", "Request timed out");
      throw new ApiFailure("unavailable", "Server unavailable");
    } finally { clearTimeout(timer); }
  }
}
