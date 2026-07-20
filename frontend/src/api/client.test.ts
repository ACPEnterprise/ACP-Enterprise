import { AxiosError, AxiosHeaders, type InternalAxiosRequestConfig } from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiClient, configureAuthentication } from "./client";

afterEach(() => configureAuthentication(null));

describe("authenticated API client", () => {
  it("attaches the current access token", async () => {
    configureAuthentication({ getAccessToken: () => "access-token", getActiveCompanyId: () => "company-1", refresh: vi.fn(), clear: vi.fn() });
    const response = await apiClient.get("/protected", {
      adapter: async (config) => ({ data: {}, status: 200, statusText: "OK", headers: {}, config }),
    });
    expect(response.config.headers.get("Authorization")).toBe("Bearer access-token");
    expect(response.config.headers.get("X-Company-ID")).toBe("company-1");
  });

  it("refreshes once and retries a protected request after a 401", async () => {
    let attempts = 0;
    let token = "expired-token";
    const refresh = vi.fn(async () => {
      token = "renewed-token";
      return token;
    });
    configureAuthentication({ getAccessToken: () => token, getActiveCompanyId: () => "company-1", refresh, clear: vi.fn() });

    const adapter = async (config: InternalAxiosRequestConfig) => {
      attempts += 1;
      if (attempts === 1) {
        throw new AxiosError(
          "Unauthorized",
          AxiosError.ERR_BAD_REQUEST,
          config,
          undefined,
          { data: {}, status: 401, statusText: "Unauthorized", headers: new AxiosHeaders(), config },
        );
      }
      return { data: { ok: true }, status: 200, statusText: "OK", headers: {}, config };
    };

    const response = await apiClient.get<{ ok: boolean }>("/protected", { adapter });
    expect(response.data.ok).toBe(true);
    expect(refresh).toHaveBeenCalledOnce();
    expect(attempts).toBe(2);
    expect(response.config.headers.get("Authorization")).toBe("Bearer renewed-token");
  });

  it("clears state when refresh cannot recover a 401", async () => {
    const clear = vi.fn();
    configureAuthentication({ getAccessToken: () => "expired", getActiveCompanyId: () => "company-1", refresh: vi.fn().mockResolvedValue(null), clear });
    const config = { headers: new AxiosHeaders() } as InternalAxiosRequestConfig;
    await expect(
      apiClient.get("/protected", {
        adapter: async (requestConfig) => {
          throw new AxiosError("Unauthorized", AxiosError.ERR_BAD_REQUEST, requestConfig, undefined, {
            data: {}, status: 401, statusText: "Unauthorized", headers: new AxiosHeaders(), config,
          });
        },
      }),
    ).rejects.toBeInstanceOf(AxiosError);
    expect(clear).toHaveBeenCalledOnce();
  });
});
