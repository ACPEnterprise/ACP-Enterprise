import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import { getGoogleAdsOwnerWorkspace } from "./marketing";

describe("Google Ads owner workspace API", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("loads only read-only provider evidence routes", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({ data: [] });
    get.mockResolvedValueOnce({ data: { connection_status: "not_configured" } });

    await getGoogleAdsOwnerWorkspace();

    expect(get.mock.calls.map(([path]) => path)).toEqual([
      "/api/v1/marketing/readiness",
      "/api/v1/marketing/google-ads/connection-readiness",
      "/api/v1/marketing/google-ads/account-bindings",
      "/api/v1/marketing/google-ads/sync-status",
      "/api/v1/marketing/google-ads/coverage",
      "/api/v1/marketing/google-ads/reconciliation",
    ]);
  });
});
