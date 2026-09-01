import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { LiaRoute } from "./LiaRoute";

const state = vi.hoisted(() => ({
  readinessError: false,
  briefingError: false,
  readinessRefetch: vi.fn(),
  briefingRefetch: vi.fn(),
  askMutate: vi.fn(),
}));

vi.mock("../hooks/useLia", () => ({
  useLiaReadiness: () => ({
    isPending: false,
    isError: state.readinessError,
    refetch: state.readinessRefetch,
    data: state.readinessError
      ? undefined
      : {
          state: "DETERMINISTIC_CAPABLE",
          provider_state: "AI_PROVIDER_NOT_CONFIGURED",
          policy_state: "POLICY_REQUIRED",
        },
  }),
  useLiaFoundationReadiness: () => ({
    isPending: false,
    isError: false,
    data: {
      foundation_version: "LIA.FOUNDATION.v1",
      release_profile: "LIA.READ_ONLY.v1",
      provider_state: "NOT_CONFIGURED",
      provider_configured: false,
      autonomous_mutation: false,
      production_mutation: false,
      source_states: {
        BEACON_INTELLIGENCE: "READY",
        ECONOMICS_INTELLIGENCE: "PARTIAL",
      },
      tool_count: 6,
      executable_tool_count: 0,
      permission_propagation: "REAUTHORIZE_AND_SCOPE_BEFORE_RETRIEVAL",
      conversation_retention: "NOT_CONFIGURED_NO_DURABLE_TRANSCRIPT",
      evaluation_status: "DETERMINISTIC_HARNESS_AVAILABLE",
      blockers: ["Economics adapter is pending."],
    },
  }),
  useOwnerBriefing: () => ({
    isPending: false,
    isError: state.briefingError,
    refetch: state.briefingRefetch,
    data: state.briefingError
      ? undefined
      : {
          request_id: "request",
          conversation_id: "conversation",
          classification: "KNOWN",
          answer: "Here is current authorized evidence.",
          evidence: [
            {
              domain: "jobs",
              label: "Jobs",
              authority: "AUTHORITATIVE_FACT",
              observed_at: "2026-08-30T00:00:00Z",
              freshness: "CURRENT_QUERY",
              entity_id: null,
              evidence_digest: "digest",
              count: 2,
              state: "ready=2",
            },
          ],
          limitations: ["No external provider was invoked."],
          navigation: [{ label: "Open Jobs", internal_path: "/jobs" }],
          proposals: [],
          completeness: "COMPLETE_FOR_AUTHORIZED_ADAPTERS",
          freshness: "CURRENT_QUERY",
          provider: "deterministic-acp",
          provider_version: "v1",
          policy_version: "v1",
          evidence_digest: "digest",
          authorization_version: 1,
          generated_at: "2026-08-30T00:00:00Z",
        },
  }),
  useAskLia: () => ({
    mutate: state.askMutate,
    isPending: false,
    isError: false,
    data: undefined,
  }),
}));

describe("LIA workspace", () => {
  it("renders truthful provider gating and evidence on phone-sized content", () => {
    render(
      <MemoryRouter>
        <LiaRoute />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("heading", { name: "Ask LIA" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Generative explanations await/),
    ).toBeInTheDocument();
    expect(screen.getByText("LIA.READ_ONLY.v1")).toBeInTheDocument();
    expect(screen.getByText("Autonomous mutation")).toBeInTheDocument();
    expect(screen.getByText("Disabled")).toBeInTheDocument();
    expect(screen.getByText("Why LIA said this")).toBeInTheDocument();
    expect(
      screen.getByRole("textbox", { name: "Ask LIA a question" }),
    ).toBeInTheDocument();
  });

  it("offers explicit recovery for readiness and briefing failures", () => {
    state.readinessError = true;
    state.briefingError = true;
    render(
      <MemoryRouter>
        <LiaRoute />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Retry readiness" }));
    fireEvent.click(screen.getByRole("button", { name: "Retry briefing" }));
    expect(state.readinessRefetch).toHaveBeenCalledOnce();
    expect(state.briefingRefetch).toHaveBeenCalledOnce();
    state.readinessError = false;
    state.briefingError = false;
  });

  it("passes only opaque Customer context for server-side authorization", () => {
    const customerId = "11111111-1111-4111-8111-111111111111";
    render(
      <MemoryRouter
        initialEntries={[
          `/lia?contextDomain=customers&contextId=${customerId}`,
        ]}
      >
        <LiaRoute />
      </MemoryRouter>,
    );
    expect(screen.getByText(/minimum-necessary Customer context/i)).toBeVisible();
    fireEvent.change(screen.getByRole("textbox", { name: "Ask LIA a question" }), {
      target: { value: "What open work exists?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(state.askMutate).toHaveBeenCalledWith(
      {
        question: "What open work exists?",
        conversation_id: undefined,
        context: { domain: "customers", entity_id: customerId },
      },
      expect.any(Object),
    );
  });

  it("passes only opaque Invoice context for server-side authorization", () => {
    const invoiceId = "7dc24d7f-94cc-4a25-a9b6-5a5e8aa36947";
    render(
      <MemoryRouter
        initialEntries={[
          `/lia?contextDomain=invoicing&contextId=${invoiceId}`,
        ]}
      >
        <LiaRoute />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByRole("textbox", { name: "Ask LIA a question" }), {
      target: { value: "What is the Invoice state?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(state.askMutate).toHaveBeenCalledWith(
      {
        question: "What is the Invoice state?",
        conversation_id: undefined,
        context: { domain: "invoicing", entity_id: invoiceId },
      },
      expect.any(Object),
    );
  });
});
