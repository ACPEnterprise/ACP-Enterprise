import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as estimatesApi from "../api/estimates";
import { EstimatesRoute } from "./EstimatesRoute";

let permissions = new Set<string>();
vi.mock("../auth", () => ({ useHasPermission: (code: string) => permissions.has(code) }));
vi.mock("../api/estimates", () => ({
  listEstimates: vi.fn().mockResolvedValue({
    total: 1,
    items: [{ id: "estimate-1", branch_id: "branch-1", customer_id: "customer-1", service_location_id: null, estimate_number: "EST-000001", status: "draft", acceptance_status: "not_requested", version: 1, proposal_title: "Heating proposal", currency: "USD", total_amount: "97.20", expires_at: null, updated_at: "2026-08-30T12:00:00Z" }],
  }),
  getEstimate: vi.fn().mockResolvedValue({
    id: "estimate-1", branch_id: "branch-1", customer_id: "customer-1", estimate_number: "EST-000001", status: "draft", acceptance_status: "not_requested", version: 1,
    current_revision: { id: "revision-1", revision_number: 1, proposal_title: "Heating proposal", currency: "USD", subtotal_amount: "100.00", discount_type: "fixed", discount_value: "10.00", discount_amount: "10.00", taxable_basis: "90.00", tax_amount: "7.20", total_amount: "97.20", customer_message: null, terms: null, lines: [{ id: "line-1", title: "Heating service", description: null, snapshot_id: "snapshot-1", snapshot_digest: "a".repeat(64), quantity: "1", unit_price: "100", line_total: "100", currency: "USD", option_group_id: "group-1", option_id: "option-1", discount_allocation: "10", discounted_basis: "90", tax_amount: "7.20", taxable: true }] },
  }),
  createEstimate: vi.fn(), reviseEstimate: vi.fn(),
}));

function renderRoute(path = "/estimates") {
  return render(<QueryClientProvider client={new QueryClient()}><MemoryRouter initialEntries={[path]}><EstimatesRoute /></MemoryRouter></QueryClientProvider>);
}

describe("EstimatesRoute", () => {
  beforeEach(() => {
    permissions = new Set();
    vi.mocked(estimatesApi.createEstimate).mockReset();
    vi.mocked(estimatesApi.listEstimates).mockClear();
    vi.mocked(estimatesApi.getEstimate).mockClear();
  });
  it("fails closed without read permission", () => {
    renderRoute();
    expect(screen.getByText("You are not authorized to view Estimates.")).toBeVisible();
    expect(estimatesApi.listEstimates).not.toHaveBeenCalled();
    expect(estimatesApi.getEstimate).not.toHaveBeenCalled();
  });
  it("keeps management controls separate from read access", async () => {
    permissions = new Set(["COMPANY_ESTIMATE_READ"]);
    renderRoute("/estimates?id=estimate-1");
    expect((await screen.findAllByText("Heating proposal"))[0]).toBeVisible();
    expect(screen.queryByText("Create proposal")).not.toBeInTheDocument();
    expect(screen.getByText("Selected customer option")).toBeVisible();
    expect(screen.getByText("Estimate pipeline")).toBeVisible();
    expect(screen.getByText("EST-000001")).toBeVisible();
  });
  it("renders mobile-safe management controls with totals", async () => {
    permissions = new Set(["COMPANY_ESTIMATE_READ", "COMPANY_ESTIMATE_MANAGE"]);
    renderRoute("/estimates?id=estimate-1");
    expect(await screen.findByText("Create proposal")).toBeVisible();
    expect((await screen.findAllByText("Heating proposal"))[0]).toBeVisible();
    expect(screen.getAllByText("$97.20")).toHaveLength(2);
    expect(screen.getByLabelText("Discount type")).toBeVisible();
  });
  it("retains proposal evidence and hides backend details after rejection", async () => {
    permissions = new Set(["COMPANY_ESTIMATE_READ", "COMPANY_ESTIMATE_MANAGE"]);
    vi.mocked(estimatesApi.createEstimate).mockRejectedValueOnce({
      isAxiosError: true,
      response: { data: { detail: { recovery: "USER_CORRECTION_REQUIRED", message: "sql-provider-secret-canary" } } },
    });
    renderRoute();
    await screen.findByText("Create proposal");
    fireEvent.change(screen.getByLabelText("Branch ID"), { target: { value: "branch-1" } });
    fireEvent.change(screen.getByLabelText("Customer ID"), { target: { value: "customer-1" } });
    fireEvent.change(screen.getByLabelText("Commercial snapshot ID"), { target: { value: "snapshot-1" } });
    fireEvent.change(screen.getByLabelText("Proposal title"), { target: { value: "Heating proposal" } });
    fireEvent.click(screen.getByRole("button", { name: "Create immutable revision" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/requires correction/i));
    expect(screen.getByLabelText("Proposal title")).toHaveValue("Heating proposal");
    expect(screen.queryByText(/sql-provider-secret-canary/)).not.toBeInTheDocument();
  });
});
