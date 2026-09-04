import { AxiosHeaders } from "axios";
import { describe, expect, it, vi } from "vitest";

import { apiClient } from "../../api/client";
import { assignMembershipRole, createRole, disconnectQuickBooksSandbox, getQuickBooksSandboxConnection, launchQuickBooksProduction, launchQuickBooksSandbox, listMemberships } from "./api";

describe("Company role administration API", () => {
  it("uses only the audited Company-admin role and Membership boundaries", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: { id: "role-1" } });
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({ data: [] });
    const put = vi.spyOn(apiClient, "put").mockResolvedValue({ data: { id: "assignment-1" } });

    await createRole({ code: "SOURCE4_PREVIEW_ADMISSION", name: "SOURCE.4 Preview Admission", description: null });
    await listMemberships();
    await assignMembershipRole("membership-1", "role-1");

    expect(post).toHaveBeenCalledWith("/api/v1/company-admin/roles", {
      code: "SOURCE4_PREVIEW_ADMISSION", name: "SOURCE.4 Preview Admission", description: null,
    });
    expect(get).toHaveBeenCalledWith("/api/v1/company-admin/memberships");
    expect(put).toHaveBeenCalledWith("/api/v1/company-admin/memberships/membership-1/roles/role-1");
  });
});

describe("QuickBooks sandbox administration API", () => {
  it("reads and disconnects through authenticated API paths", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({ data: { status: "qbo_sandbox_connection", connection_state: "connected" } });
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: { status: "qbo_sandbox_connection", connection_state: "not_connected" } });

    expect(await getQuickBooksSandboxConnection()).toBe("connected");
    expect(await disconnectQuickBooksSandbox()).toBe("not_connected");
    expect(get).toHaveBeenCalledWith("/api/v1/integrations/qbo/connection");
    expect(post).toHaveBeenCalledWith("/api/v1/integrations/qbo/oauth/disconnect");
  });

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

  it("launches Production only with the exact Production callback", async () => {
    const callback = encodeURIComponent(
      `${window.location.origin}/api/v1/integrations/qbo/production/oauth/callback`,
    );
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({
      data: {
        status: "qbo_production_oauth_initiation",
        authorization_url:
          `https://appcenter.intuit.com/connect/oauth2?client_id=synthetic&redirect_uri=${callback}` +
          "&response_type=code&scope=com.intuit.quickbooks.accounting&state=synthetic-state",
      },
    });
    const navigate = vi.fn();

    await launchQuickBooksProduction(navigate);

    expect(post).toHaveBeenCalledWith(
      "/api/v1/integrations/qbo/production/oauth/authorize",
    );
    expect(navigate).toHaveBeenCalledOnce();
  });
});
