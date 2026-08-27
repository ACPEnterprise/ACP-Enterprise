import { AxiosHeaders } from "axios";
import { describe, expect, it, vi } from "vitest";

import { apiClient } from "../../api/client";
import { launchQuickBooksSandbox } from "./api";

describe("QuickBooks sandbox administration API", () => {
  it("navigates directly to the official Intuit authorization endpoint", async () => {
    const callback = encodeURIComponent(
      `${window.location.origin}/api/v1/integrations/qbo/oauth/callback`,
    );
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({
      data: {
        status: "sandbox_oauth_initiation",
        authorization_url:
          `https://appcenter.intuit.com/connect/oauth2?client_id=synthetic&redirect_uri=${callback}` +
          "&response_type=code&scope=com.intuit.quickbooks.accounting&state=synthetic-state",
      },
      status: 200,
      statusText: "OK",
      headers: {},
      config: { headers: new AxiosHeaders() },
    });
    const navigate = vi.fn();

    await launchQuickBooksSandbox(navigate);

    expect(post).toHaveBeenCalledWith("/api/v1/integrations/qbo/oauth/authorize");
    expect(navigate).toHaveBeenCalledOnce();
    expect(navigate.mock.calls[0]?.[0]).toMatch(/^https:\/\/appcenter\.intuit\.com\/connect\/oauth2\?/);
  });

  it("rejects a backend response pointing anywhere except official Intuit", async () => {
    vi.spyOn(apiClient, "post").mockResolvedValue({
      data: { status: "sandbox_oauth_initiation", authorization_url: "https://example.test/connect?state=unsafe" },
      status: 200,
      statusText: "OK",
      headers: {},
      config: { headers: new AxiosHeaders() },
    });
    const navigate = vi.fn();

    await expect(launchQuickBooksSandbox(navigate)).rejects.toThrow("Unexpected QuickBooks authorization destination.");
    expect(navigate).not.toHaveBeenCalled();
  });
});
