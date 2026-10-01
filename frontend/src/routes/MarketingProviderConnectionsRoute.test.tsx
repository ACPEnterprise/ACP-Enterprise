import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuth } from "../auth";
import { MarketingProviderConnectionsRoute } from "./MarketingProviderConnectionsRoute";

vi.mock("../auth", () => ({ useAuth: vi.fn() }));
vi.mock("@tanstack/react-query", () => ({ useQuery: vi.fn(), useMutation: vi.fn() }));

import { useMutation, useQuery } from "@tanstack/react-query";

describe("MarketingProviderConnectionsRoute", () => {
  beforeEach(() => {
    vi.mocked(useMutation).mockReturnValue({ mutate: vi.fn(), isPending: false, isError: false } as unknown as ReturnType<typeof useMutation>);
    vi.mocked(useAuth).mockReturnValue({ activeCompany: { id: "company-1", name: "All County", branches: [] } } as unknown as ReturnType<typeof useAuth>);
    vi.mocked(useQuery).mockReturnValue({
      isPending: false,
      isError: false,
      refetch: vi.fn(),
      data: {
        projection: {
          projection_version: "marketing-readiness.v1", company_id: "company-1", provider_family: "google_ads", as_of: "2026-09-30T12:00:00Z",
          owner_state: "CONFIGURATION_REQUIRED", owner_guidance: ["Ask a platform administrator to configure Google Ads."],
          account_discovery_state: "NOT_AVAILABLE", account_bound: false, ingestion_enabled: false,
          spend_evidence_availability: "UNAVAILABLE", last_successful_sync_at: null,
        },
        readiness: {
          connection_status: "configuration_required",
          environment: "beta",
          oauth_client_configured: true,
          callback_configured: true,
          developer_token_configured: false,
          environment_safe_secret_custody: false,
          live_ingestion_enabled: false,
          authorization_available: false,
          granted_scopes: [],
          connected_at: null,
          bound_account_count: 0,
          blockers: ["developer_token_not_configured"],
        },
        bindings: [], sync: [], coverage: [], reconciliation: [],
      },
    } as unknown as ReturnType<typeof useQuery>);
  });

  it("shows secret-safe readiness and cannot initiate authorization or sync", () => {
    render(<MarketingProviderConnectionsRoute/>);
    expect(screen.getByRole("button", { name: /connect google ads/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /start read-only sync/i })).toBeDisabled();
    expect(screen.getByText(/No authorization request has been started/i)).toBeInTheDocument();
    expect(screen.getByText("CONFIGURATION REQUIRED")).toBeInTheDocument();
    expect(screen.getByText(/Ask a platform administrator/i)).toBeInTheDocument();
    expect(screen.queryByText(/refresh.token|client.secret/i)).not.toBeInTheDocument();
  });
});
