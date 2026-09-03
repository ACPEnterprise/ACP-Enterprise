import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

const renderRoute = () => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><MemoryRouter><PaymentsRoute /></MemoryRouter></QueryClientProvider>);

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
    expect(screen.queryByText("Submit payment collection")).not.toBeInTheDocument();
  });
  it("shows only opaque collection controls to collectors", async () => {
    permissions = new Set(["COMPANY_PAYMENT_READ", "COMPANY_PAYMENT_COLLECT"]); renderRoute();
    expect(await screen.findByText("Submit payment collection")).toBeVisible();
    expect(screen.getByLabelText("Opaque payment method")).toBeVisible();
  });
  it("shows a safe uncertain outcome when provider submission fails", async () => {
    permissions = new Set(["COMPANY_PAYMENT_READ", "COMPANY_PAYMENT_COLLECT"]);
    vi.mocked(paymentsApi.collectPayment).mockRejectedValueOnce(new Error("raw provider secret"));
    renderRoute();
    await screen.findByText("Submit payment collection");
    await userEvent.type(screen.getByLabelText("Branch ID"), "branch-1");
    await userEvent.type(screen.getByLabelText("Customer ID"), "customer-1");
    await userEvent.type(screen.getByLabelText("Amount"), "10.00");
    await userEvent.type(screen.getByLabelText("Opaque payment method"), "opaque_test");
    await userEvent.click(screen.getByRole("button", { name: "Submit to provider" }));
    expect(await screen.findByText(/Do not assume money moved/)).toBeVisible();
    expect(screen.queryByText(/raw provider secret/)).not.toBeInTheDocument();
  });
});
