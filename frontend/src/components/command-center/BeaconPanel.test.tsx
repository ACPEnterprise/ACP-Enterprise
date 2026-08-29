import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { BeaconSignal } from "../../api/beacon";
import { BeaconPanel } from "./BeaconPanel";

const signal: BeaconSignal = {
  id: "signal-id",
  condition_key: "condition-id",
  evidence_digest: "a".repeat(64),
  definition_id: "revenue.past_due_invoices",
  definition_version: 1,
  rule_code: "revenue.past_due_invoices",
  source: "invoices",
  title: "Issued invoices are past due",
  category: "revenue",
  severity: "important",
  priority: {
    band: "immediate",
    score: 337,
    rank: 1,
    ranking_factors: [
      {
        name: "severity",
        value: "important",
        unit: null,
        availability: "measured",
        contribution: 300,
        explanation: "Important severity contributes 300 points.",
      },
    ],
    explanation:
      "Important severity contributes 300 points; measured ranking factors contribute 37 points.",
    evaluated_at: "2026-07-28T16:00:00Z",
    tie_break_semantics:
      "Higher score first; ties resolve by severity, source, rule code, then stable signal identifier.",
  },
  lifecycle: {
    status: "active",
    latest_event: null,
    temporarily_suppressed: false,
  },
  confidence: {
    level: "high",
    basis: "Authoritative Company-scoped records.",
  },
  supporting_facts: [
    {
      name: "past_due_invoice_count",
      value: 2,
      source: "invoices",
      measured_at: "2026-07-28T16:00:00Z",
      evidence: [
        {
          entity_type: "invoice",
          entity_id: "invoice-1",
          event_id: "event-1",
          event_type: "invoice.created",
          occurred_at: "2026-07-20T16:00:00Z",
        },
      ],
      unit: "invoices",
    },
  ],
  recommended_action: "Review the authoritative invoice records.",
  created_at: "2026-07-28T16:00:00Z",
  expires_at: "2099-07-28T16:15:00Z",
  expiration_policy: "replace_on_next_evaluation",
  escalation: null,
  workflow: null,
};

const panelProps = {
  snoozedSignals: [],
  canReview: false,
  canOwn: false,
  canAssign: false,
  currentUserId: "user-a",
  evaluatedAt: "2026-07-28T16:00:00Z",
  loading: false,
  error: false,
  lifecycleError: false,
  lifecyclePending: false,
  workflowError: false,
  workflowPending: false,
  onLifecycleAction: vi.fn(),
  onWorkflowAction: vi.fn(),
  retry: vi.fn(),
};

describe("BeaconPanel", () => {
  it("renders explainable signals and measured facts", () => {
    render(
      <BeaconPanel
        {...panelProps}
        signals={[signal]}
      />,
    );
    expect(screen.getByRole("heading", { name: "Beacon" })).toBeInTheDocument();
    expect(screen.getByText(signal.title)).toBeInTheDocument();
    expect(screen.getByText("2 invoices")).toBeInTheDocument();
    expect(screen.getByText(/Review the authoritative invoice records/)).toBeInTheDocument();
    expect(screen.getByText("high confidence")).toBeInTheDocument();
    expect(screen.getByText("Immediate priority")).toBeInTheDocument();
    expect(screen.getByText("Important severity")).toBeInTheDocument();
    expect(screen.getByText("First for owner attention")).toBeInTheDocument();
    expect(
      screen.getByText(/measured ranking factors contribute 37 points/),
    ).toBeInTheDocument();
  });

  it("keeps lower-priority signals in stable queue order", () => {
    const lowerPriority = {
      ...signal,
      id: "second-signal",
      title: "Jobs remain paused",
      source: "jobs" as const,
      category: "operations" as const,
      priority: {
        ...signal.priority,
        band: "important" as const,
        score: 204,
        rank: 2,
      },
    };
    render(
      <BeaconPanel
        {...panelProps}
        signals={[signal, lowerPriority]}
      />,
    );
    const queue = screen.getByRole("list", { name: "Owner attention queue" });
    expect(queue).toHaveTextContent(signal.title);
    expect(queue).toHaveTextContent(lowerPriority.title);
    expect(screen.getByText(/Priority 2 · operations · jobs/)).toBeInTheDocument();
  });

  it("renders an honest empty state", () => {
    render(
      <BeaconPanel
        {...panelProps}
        signals={[]}
      />,
    );
    expect(screen.getByText("No active Beacon signals")).toBeInTheDocument();
    expect(screen.queryByText(/all systems operational/i)).not.toBeInTheDocument();
  });

  it("renders an unavailable state and supports retry", () => {
    const retry = vi.fn();
    render(
      <BeaconPanel
        {...panelProps}
        signals={undefined}
        error
        retry={retry}
      />,
    );
    expect(screen.getByText("Beacon signals unavailable")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it("shows lifecycle controls only with review permission", () => {
    const onLifecycleAction = vi.fn();
    const onWorkflowAction = vi.fn();
    const { rerender } = render(
      <BeaconPanel
        {...panelProps}
        signals={[signal]}
        onLifecycleAction={onLifecycleAction}
        onWorkflowAction={onWorkflowAction}
      />,
    );
    expect(
      screen.queryByRole("button", { name: "Acknowledge" }),
    ).not.toBeInTheDocument();

    rerender(
      <BeaconPanel
        {...panelProps}
        canReview
        signals={[signal]}
        onLifecycleAction={onLifecycleAction}
        onWorkflowAction={onWorkflowAction}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Acknowledge responsibility" }),
    );
    expect(onWorkflowAction).toHaveBeenCalledWith(
      signal,
      "acknowledge",
      undefined,
      undefined,
    );
    expect(screen.queryByRole("button", { name: /dismiss/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /resolve/i })).not.toBeInTheDocument();
  });

  it("shows ownership state and gates take, release, and transfer controls", () => {
    const onWorkflowAction = vi.fn();
    const { rerender } = render(
      <BeaconPanel
        {...panelProps}
        canOwn
        signals={[signal]}
        onWorkflowAction={onWorkflowAction}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Take ownership" }));
    expect(onWorkflowAction).toHaveBeenCalledWith(signal, "claim", 0);

    const owned = {
      ...signal,
      workflow: {
        company_id: "company-a",
        branch_id: "branch-a",
        condition_key: signal.condition_key,
        signal_id: signal.id,
        definition_id: signal.definition_id,
        definition_version: 1,
        evidence_digest: signal.evidence_digest,
        workflow_version: 2,
        acknowledged: true,
        acknowledged_by_user_id: "user-a",
        acknowledged_at: "2026-07-28T16:05:00Z",
        owner_user_id: "user-a",
        owned_since: "2026-07-28T16:06:00Z",
        last_action: "claim" as const,
        last_actor_user_id: "user-a",
        updated_at: "2026-07-28T16:06:00Z",
      },
    };
    rerender(
      <BeaconPanel
        {...panelProps}
        canAssign
        canOwn
        signals={[owned]}
        onWorkflowAction={onWorkflowAction}
      />,
    );
    expect(screen.getByText(/Owner user-a \(you\)/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Release ownership" }));
    expect(onWorkflowAction).toHaveBeenCalledWith(owned, "release", 2);
    expect(screen.getByRole("button", { name: "Transfer ownership" })).toBeDisabled();
  });
});
