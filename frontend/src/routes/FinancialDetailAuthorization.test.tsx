import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as invoicesApi from "../api/invoices";
import * as paymentsApi from "../api/payments";
import { InvoiceDetailRoute } from "./InvoiceDetailRoute";
import { PaymentDetailRoute } from "./PaymentDetailRoute";

let permissions = new Set<string>();

vi.mock("../auth", () => ({
  useHasPermission: (code: string) => permissions.has(code),
}));
vi.mock("../api/invoices", () => ({
  getInvoice: vi.fn(),
  getInvoiceOfficeDetail: vi.fn(),
  getCustomerBalance: vi.fn(),
  listInvoices: vi.fn(),
  createInvoice: vi.fn(),
  issueInvoice: vi.fn(),
}));
vi.mock("../api/payments", () => ({
  getPaymentReceipt: vi.fn(),
  listPaymentReceipts: vi.fn(),
  collectPayment: vi.fn(),
  applyPayment: vi.fn(),
  refundPayment: vi.fn(),
}));

function renderDetail(path: string) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/invoices/:invoiceId" element={<InvoiceDetailRoute />} />
          <Route path="/payments/:receiptId" element={<PaymentDetailRoute />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("financial object-detail authorization", () => {
  beforeEach(() => {
    permissions = new Set();
    vi.clearAllMocks();
  });

  it("does not request an Invoice object without read authority", () => {
    renderDetail("/invoices/valid-but-unauthorized-id");
    expect(screen.getByText(/not authorized to view this Invoice/i)).toBeVisible();
    expect(invoicesApi.getInvoice).not.toHaveBeenCalled();
  });

  it("does not request a Payment object without read authority", () => {
    renderDetail("/payments/valid-but-unauthorized-id");
    expect(screen.getByText(/not authorized to view this Payment/i)).toBeVisible();
    expect(paymentsApi.getPaymentReceipt).not.toHaveBeenCalled();
  });

  it("returns from an authorized Payment to its authoritative Customer", async () => {
    permissions = new Set(["COMPANY_PAYMENT_READ"]);
    vi.mocked(paymentsApi.getPaymentReceipt).mockResolvedValue({
      id: "receipt-1", branch_id: "branch-1", customer_id: "customer-1", intent_id: "intent-1", currency: "USD", status: "settled", captured_amount: "25.00", available_amount: "0.00", applied_amount: "25.00", refunded_amount: "0.00", disputed_amount: "0.00", version: 1, captured_at: "2026-09-01T00:00:00Z",
    });
    renderDetail("/payments/receipt-1");
    expect(await screen.findByRole("link", { name: "Back to Customer" })).toHaveAttribute("href", "/customers/customer-1");
  });
});
