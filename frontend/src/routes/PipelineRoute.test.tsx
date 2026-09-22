import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PipelineRoute } from "./PipelineRoute";
import { useAuth, useHasPermission } from "../auth";
import { useCreateLead, useLeads } from "../hooks/usePipeline";

vi.mock("../auth");
vi.mock("../hooks/usePipeline");

function renderRoute(path = "/pipeline?view=needs_attention") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}><PipelineRoute /></MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("PipelineRoute", () => {
  beforeEach(() => {
    vi.mocked(useHasPermission).mockReturnValue(true);
    vi.mocked(useAuth).mockReturnValue({ activeCompany: { branches: [{ id: "branch-1", name: "MAIN" }] } } as ReturnType<typeof useAuth>);
    vi.mocked(useCreateLead).mockReturnValue({ isError: false, isPending: false, mutateAsync: vi.fn() } as unknown as ReturnType<typeof useCreateLead>);
    vi.mocked(useLeads).mockReturnValue({ isPending: false, isError: false, data: { total: 1, filters: {}, items: [{ id: "lead-1", company_id: "company-1", branch_id: "branch-1", customer_id: "customer-1", prospect_name: "Smith Family", contact_phone: null, contact_email: null, lead_source: "incoming_phone", source_detail: null, source_system: null, service_category: "plumbing", service_need: "Leaking water heater", assigned_user_id: null, stage: "new", created_at: "2026-09-22T12:00:00Z", last_action_at: null, next_action_type: null, next_action_due_at: null, contact_attempt_count: 0, appointment_id: null, job_id: null, estimate_id: null, attributable_value_minor: null, value_currency: null, value_authority: null, attention_state: "new_uncontacted", version: 1 }] } } as ReturnType<typeof useLeads>);
  });

  it("shows an operator-friendly needs-attention queue and source navigation", () => {
    renderRoute();
    expect(screen.getByRole("heading", { name: "Pipeline" })).toBeVisible();
    expect(screen.getByText("Smith Family")).toBeVisible();
    expect(screen.getByText("New — contact needed")).toBeVisible();
    expect(screen.getByRole("link", { name: "Open Customer" })).toHaveAttribute("href", "/customers/customer-1");
  });

  it("fails closed without Customer read authority", () => {
    vi.mocked(useHasPermission).mockReturnValue(false);
    renderRoute();
    expect(screen.getByText("You are not authorized to view Pipeline.")).toBeVisible();
    expect(useLeads).toHaveBeenCalledWith("needs_attention", false);
  });
});
