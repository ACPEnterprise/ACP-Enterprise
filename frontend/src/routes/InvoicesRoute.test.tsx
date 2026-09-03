import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as invoicesApi from "../api/invoices";
import { InvoicesRoute } from "./InvoicesRoute";

let permissions = new Set<string>();
vi.mock("../auth", () => ({
  useHasPermission: (code: string) => permissions.has(code),
}));
vi.mock("../api/invoices", () => ({
  getInvoiceWorkspace: vi
    .fn()
    .mockImplementation(async (filters: { query?: string }) => filters.query ? [] : [
      {
        id: "invoice-1",
        invoice_number: "INV-000001",
        status: "issued",
        open_amount: "125.00",
        total_amount: "125.00",
        currency: "USD",
        customer_display_name: "Synthetic Customer",
        customer_number: "CUS-000001",
        job_number: "JOB-000001",
        service_location_label: "123 Test Street",
        due_date: "2026-08-01",
        age_days: 32,
        attention_reasons: ["INVOICE_OVERDUE"],
      },
    ]),
  getCustomerBalance: vi.fn(),
  listInvoices: vi
    .fn()
    .mockResolvedValue([
      {
        id: "invoice-1",
        invoice_number: "INV-000001",
        status: "issued",
        open_amount: "125.00",
        currency: "USD",
      },
    ]),
  createInvoice: vi.fn(),
  issueInvoice: vi.fn(),
  getInvoice: vi.fn(),
  creditInvoice: vi.fn(),
  writeOffInvoice: vi.fn(),
  voidInvoice: vi.fn(),
}));

function renderRoute() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <InvoicesRoute />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("InvoicesRoute", () => {
  beforeEach(() => {
    permissions = new Set();
    vi.mocked(invoicesApi.getInvoiceWorkspace).mockClear();
  });
  it("fails closed without Invoice read permission", () => {
    renderRoute();
    expect(
      screen.getByText("You are not authorized to view Invoices."),
    ).toBeVisible();
    expect(invoicesApi.getInvoiceWorkspace).not.toHaveBeenCalled();
  });
  it("shows receivables without mutation controls for read-only users", async () => {
    permissions = new Set(["COMPANY_INVOICE_READ"]);
    renderRoute();
    expect(await screen.findByText("INV-000001")).toBeVisible();
    expect(
      screen.queryByText("Create from accepted work"),
    ).not.toBeInTheDocument();
  });
  it("exposes accepted-work creation only with manage permission", async () => {
    permissions = new Set(["COMPANY_INVOICE_READ", "COMPANY_INVOICE_MANAGE"]);
    renderRoute();
    expect(await screen.findByText("Create from accepted work")).toBeVisible();
    expect(screen.getByLabelText("Estimate ID")).toBeVisible();
    expect(screen.getByLabelText("Job ID")).toBeVisible();
  });
  it("filters the operational receivables queue without changing authority", async () => {
    permissions = new Set(["COMPANY_INVOICE_READ"]);
    renderRoute();
    expect(await screen.findByText("INV-000001")).toBeVisible();
    await userEvent.type(screen.getByLabelText("Search invoices"), "missing");
    expect(await screen.findByText("No invoices match these filters.")).toBeVisible();
  });
});
