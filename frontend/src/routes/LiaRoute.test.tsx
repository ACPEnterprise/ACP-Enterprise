import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { LiaRoute } from "./LiaRoute";

vi.mock("../hooks/useLia", () => ({
  useLiaReadiness: () => ({ isPending: false, isError: false, data: {
    state: "PRODUCT_READY_PROVIDER_GATE",
    provider_state: "AI_PROVIDER_NOT_CONFIGURED",
  }}),
  useOwnerBriefing: () => ({ isPending: false, isError: false, data: {
    request_id: "request", conversation_id: "conversation", classification: "KNOWN",
    answer: "Here is current authorized evidence.", evidence: [{ domain: "jobs", label: "Jobs", authority: "AUTHORITATIVE_FACT", observed_at: "2026-08-30T00:00:00Z", freshness: "CURRENT_QUERY", entity_id: null, evidence_digest: "digest", count: 2, state: "ready=2" }],
    limitations: ["No external provider was invoked."], navigation: [{ label: "Open Jobs", internal_path: "/jobs" }], proposals: [], completeness: "COMPLETE_FOR_AUTHORIZED_ADAPTERS", freshness: "CURRENT_QUERY", provider: "deterministic-acp", provider_version: "v1", policy_version: "v1", evidence_digest: "digest", authorization_version: 1, generated_at: "2026-08-30T00:00:00Z",
  }}),
  useAskLia: () => ({ mutate: vi.fn(), isPending: false, isError: false, data: undefined }),
}));

describe("LIA workspace", () => {
  it("renders truthful provider gating and evidence on phone-sized content", () => {
    render(<MemoryRouter><LiaRoute /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Ask LIA" })).toBeInTheDocument();
    expect(screen.getByText(/Generative explanations await/)).toBeInTheDocument();
    expect(screen.getByText("Why LIA said this")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Ask LIA a question" })).toBeInTheDocument();
  });
});
