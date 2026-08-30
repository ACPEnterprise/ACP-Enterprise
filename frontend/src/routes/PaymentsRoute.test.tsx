import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as paymentsApi from "../api/payments";
import { PaymentsRoute } from "./PaymentsRoute";

let permissions = new Set<string>();
vi.mock("../auth", () => ({ useHasPermission: (code: string) => permissions.has(code) }));
vi.mock("../api/payments", () => ({
  listPaymentReceipts: vi.fn().mockResolvedValue([{ id: "receipt-1", status: "unapplied", available_amount: "20.00", currency: "USD" }]),
  collectPayment: vi.fn(), applyPayment: vi.fn(), refundPayment: vi.fn(), getPaymentReceipt: vi.fn(),
}));

const renderRoute = () => render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><PaymentsRoute /></MemoryRouter></QueryClientProvider>);

describe("PaymentsRoute", () => {
  beforeEach(() => { permissions = new Set(); vi.mocked(paymentsApi.listPaymentReceipts).mockClear(); });
  it("fails closed without payment read permission", () => {
    renderRoute();
    expect(screen.getByText("You are not authorized to view Payments.")).toBeVisible();
    expect(paymentsApi.listPaymentReceipts).not.toHaveBeenCalled();
  });
  it("separates read and collect controls", async () => {
    permissions = new Set(["COMPANY_PAYMENT_READ"]); renderRoute();
    expect(await screen.findByText(/20.00 USD available/)).toBeVisible();
    expect(screen.queryByText("Collect a payment")).not.toBeInTheDocument();
  });
  it("shows only opaque collection controls to collectors", async () => {
    permissions = new Set(["COMPANY_PAYMENT_READ", "COMPANY_PAYMENT_COLLECT"]); renderRoute();
    expect(await screen.findByText("Collect a payment")).toBeVisible();
    expect(screen.getByLabelText("Opaque payment method")).toBeVisible();
  });
});
