import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { BeaconSignal } from "../../api/beacon";
import { BeaconPanel } from "./BeaconPanel";

const signal: BeaconSignal = {
  id: "signal-id",
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
  expires_at: "2026-07-28T16:15:00Z",
  expiration_policy: "replace_on_next_evaluation",
};

describe("BeaconPanel", () => {
  it("renders explainable signals and measured facts", () => {
    render(
      <BeaconPanel
        signals={[signal]}
        loading={false}
        error={false}
        retry={vi.fn()}
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
        signals={[signal, lowerPriority]}
        loading={false}
        error={false}
        retry={vi.fn()}
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
        signals={[]}
        loading={false}
        error={false}
        retry={vi.fn()}
      />,
    );
    expect(screen.getByText("No active Beacon signals")).toBeInTheDocument();
    expect(screen.queryByText(/all systems operational/i)).not.toBeInTheDocument();
  });

  it("renders an unavailable state and supports retry", () => {
    const retry = vi.fn();
    render(
      <BeaconPanel
        signals={undefined}
        loading={false}
        error
        retry={retry}
      />,
    );
    expect(screen.getByText("Beacon signals unavailable")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledOnce();
  });
});
