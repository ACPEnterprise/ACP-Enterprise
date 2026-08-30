import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as invoicesApi from "../api/invoices";
import { InvoicesRoute } from "./InvoicesRoute";

let permissions = new Set<string>();
vi.mock("../auth", () => ({
  useHasPermission: (code: string) => permissions.has(code),
}));
vi.mock("../api/invoices", () => ({
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
    vi.mocked(invoicesApi.listInvoices).mockClear();
  });
  it("fails closed without Invoice read permission", () => {
    renderRoute();
    expect(
      screen.getByText("You are not authorized to view Invoices."),
    ).toBeVisible();
    expect(invoicesApi.listInvoices).not.toHaveBeenCalled();
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
});
