import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "./api";
import { MigrationWorkspace } from "./MigrationWorkspace";

vi.mock("./api");

const readiness: api.MigrationReadiness = {
  overall_status: "external_owner_gate",
  current_phase: "owner_ready",
  authority_digest: "a".repeat(64),
  reconciliation_digest: "b".repeat(64),
  stale: false,
  safe_failure_code: null,
  go_no_go: {
    state: "external_auth_required",
    activation_eligible: false,
    blockers: ["real_hcp_final_delta_required"],
  },
  historical_window: {
    starts_on: null,
    ends_on: "2026-08-30",
    opening_evidence_state: "owner_decision_required",
    completeness: "configuration_required",
  },
  sources: [
    {
      source: "HCP",
      environment: "protected_rehearsal",
      status: "external_owner_gate",
      connection_state: "rehearsal_complete_replay_verified",
      acquisition_state: "baseline_complete",
      manifest_state: "sealed",
      delta_state: "external_authorization_required",
      freeze_state: "not_frozen",
      authority_digest: "a".repeat(64),
    },
    {
      source: "QBO Development",
      environment: "sandbox",
      status: "ready",
      connection_state: "active_verified",
      acquisition_state: "representative_history_reconciled",
      manifest_state: "sealed_replay_verified",
      delta_state: "controlled_change_verified",
      freeze_state: "not_applicable",
      authority_digest: "b".repeat(64),
    },
    {
      source: "QBO Production",
      environment: "production_disabled",
      status: "external_owner_gate",
      connection_state: "external_authorization_required",
      acquisition_state: "not_started",
      manifest_state: "not_available",
      delta_state: "not_started",
      freeze_state: "not_frozen",
      authority_digest: "c".repeat(64),
    },
  ],
  counts: [
    {
      domain: "Customers",
      source: 10,
      migrated: 9,
      held: 1,
      exception: 0,
      non_applicable: 0,
      deferred: 0,
      unresolved: 0,
      delta: 0,
    },
  ],
  timeline: [
    { phase: "Preflight", status: "ready" },
    { phase: "Source freeze", status: "external_owner_gate" },
  ],
  authority_states: [{ fact: "Real overlap", state: "unresolved" }],
  owner_decisions: [
    { decision: "Chart of Accounts mapping", state: "owner_decision_required" },
  ],
  decision_packets: [
    {
      decision_id: "HCP.CANCELED_BALANCE_JOBS",
      question: "How should canceled balances be treated?",
      current_evidence: "296 source Jobs remain held.",
      options: ["retain_hold", "explicit_exception"],
      recommended_default: "retain_hold",
      risk: "False AR.",
      unlocks: "Final Job disposition.",
      state: "owner_decision_required",
    },
  ],
  freeze_authority: {
    state: "external_authorization_required",
    required_authority: "owner_go_no_go_actor",
    sources: ["HCP"],
    evidence: "immutable_source_timestamps_and_manifest_digests",
    late_change_behavior: "invalidate_delta_and_return_to_reconciliation",
    reopen_behavior: "new_freeze_generation_required",
  },
  run_history: [
    {
      run_id: "safe-run-id",
      source: "HCP",
      state: "completed",
      reconciliation: "plan_conforming",
      replay: "verified",
      holds: 1,
      exceptions: 2,
    },
  ],
  recovery_state: "completed_runs_replay_safe",
};

function renderWorkspace() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MigrationWorkspace />
    </QueryClientProvider>,
  );
}

describe("MigrationWorkspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getMigrationReadiness).mockResolvedValue(readiness);
  });

  it("presents source gates, accounting, decisions, history, and recovery safely", async () => {
    renderWorkspace();
    expect(
      await screen.findByRole("heading", { name: "Migration readiness" }),
    ).toBeInTheDocument();
    expect(screen.getByText("QBO Development")).toBeInTheDocument();
    expect(screen.getByText("QBO Production")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Source = migrated + held + exception + non-applicable + deferred + unresolved.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Chart of Accounts mapping")).toBeInTheDocument();
    expect(screen.getByText("How should canceled balances be treated?")).toBeInTheDocument();
    expect(screen.getByText("Real Hcp Final Delta Required")).toBeInTheDocument();
    expect(screen.getByText("Real overlap")).toBeInTheDocument();
    expect(screen.getByText("safe-run-id")).toBeInTheDocument();
    expect(screen.getByText("Start: Not selected")).toBeInTheDocument();
    expect(
      screen.queryByText(/token|secret|customer name/i),
    ).not.toBeInTheDocument();
  });

  it("fails visibly without fabricating readiness when the API fails", async () => {
    vi.mocked(api.getMigrationReadiness).mockRejectedValue(
      new Error("protected detail"),
    );
    renderWorkspace();
    expect(
      await screen.findByText(
        "Migration readiness is unavailable. No readiness state was inferred.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("protected detail")).not.toBeInTheDocument();
  });
});
