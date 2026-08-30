import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as auth from "../auth";
import * as api from "../api/ownerOperations";
import { OwnerOperationsRoute } from "./OwnerOperationsRoute";

vi.mock("../auth", async (original) => ({ ...(await original()), useAuth: vi.fn() }));

describe("OwnerOperationsRoute", () => {
  beforeEach(() => {
    vi.mocked(auth.useAuth).mockReturnValue({ user: { id: "user-1", normalized_email: "owner@example.test", first_name: "Owner", last_name: "Test", display_name: "Owner Test", email_verified_at: "2026-01-01" }, activeCompany: { id: "company-1", code: "ACP", name: "Synthetic Company", membership_id: "membership-1", default_branch_id: "branch-1", has_all_branch_access: false, branches: [{ id: "branch-1", code: "MAIN", name: "Main Branch", is_primary: true }] }, permissionCodes: ["COMPANY_ADMINISTER", "COMPANY_ROLE_READ", "COMPANY_MEMBERSHIP_READ", "COMPANY_AUDIT_READ"], status: "authenticated", signIn: vi.fn(), signOut: vi.fn(), signOutAll: vi.fn(), requireReauthentication: vi.fn() });
    vi.spyOn(api, "getSystemReadiness").mockResolvedValue({ state: "DEGRADED", application: "ACP Enterprise", version: "test-sha", environment: "preview", observed_at: "2026-08-30T12:00:00Z", components: [{ component: "database", state: "HEALTHY", required: true, classification: "HARD_REQUIRED", reason: "connected", observed_at: "2026-08-30T12:00:00Z", safe_facts: { schema_head: "head" } }] });
    vi.spyOn(api, "getLaunchRoleMatrix").mockResolvedValue([{ code: "TECHNICIAN", purpose: "Field execution", permission_codes: ["COMPANY_JOB_EXECUTE"], branch_access_required: true }]);
    vi.spyOn(api, "getIntegrationReadiness").mockResolvedValue({ qbo: "not_connected", migration: { overall_status: "BLOCKED", current_phase: "qualification", authority_digest: "safe", reconciliation_digest: "safe", stale: false, safe_failure_code: null, historical_window: { starts_on: null, ends_on: "2026-08-30", opening_evidence_state: "UNKNOWN", completeness: "UNKNOWN" }, sources: [], counts: [], timeline: [], authority_states: [], owner_decisions: [{ decision: "source_acceptance", state: "OWNER_DECISION" }], run_history: [], recovery_state: "BLOCKED" } });
    vi.spyOn(api, "listMembershipReadiness").mockResolvedValue([{ id: "membership-1", user_id: "user-1", company_id: "company-1", status: "active", default_branch_id: "branch-1", has_all_branch_access: false, invited_at: "2026-01-01", accepted_at: "2026-01-02", revoked_at: null, created_at: "2026-01-01", updated_at: "2026-01-02" }]);
  });

  it("shows truthful readiness without granting execution controls", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><MemoryRouter><OwnerOperationsRoute /></MemoryRouter></QueryClientProvider>);
    expect(await screen.findByText("database")).toBeInTheDocument();
    expect(screen.getByText("Synthetic Company")).toBeInTheDocument();
    expect(await screen.findByText("not_connected")).toBeInTheDocument();
    expect(await screen.findByText(/TECHNICIAN/)).toBeInTheDocument();
    expect(await screen.findByText("user-1")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /connect quickbooks|run migration|grant/i })).not.toBeInTheDocument();
  });
});
