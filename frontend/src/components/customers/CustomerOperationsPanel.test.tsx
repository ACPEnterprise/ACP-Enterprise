import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as estimateHooks from "../../hooks/useEstimates";
import * as invoiceHooks from "../../hooks/useInvoices";
import * as jobHooks from "../../hooks/useJobs";
import * as paymentHooks from "../../hooks/usePayments";
import * as schedulingHooks from "../../hooks/useScheduling";
import { CustomerOperationsPanel } from "./CustomerOperationsPanel";

vi.mock("../../hooks/useEstimates");
vi.mock("../../hooks/useInvoices");
vi.mock("../../hooks/useJobs");
vi.mock("../../hooks/usePayments");
vi.mock("../../hooks/useScheduling");
vi.mock("../../auth", () => ({ useHasPermission: () => true }));

const query = (data: unknown) => ({
  data,
  isLoading: false,
  isError: false,
  isSuccess: true,
});

describe("CustomerOperationsPanel", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(jobHooks.useJobs).mockReturnValue(query({
      items: [], total_count: 7, page: 1, page_size: 25, total_pages: 1,
    }) as never);
    vi.mocked(schedulingHooks.useAppointments).mockReturnValue(query({
      items: [], total_count: 3, page: 1, page_size: 50, total_pages: 1,
    }) as never);
    vi.mocked(estimateHooks.useEstimates).mockReturnValue(query({
      items: [], total: 4,
    }) as never);
    vi.mocked(invoiceHooks.useInvoiceWorkspace).mockReturnValue(query([]) as never);
    vi.mocked(invoiceHooks.useCustomerBalance).mockReturnValue(query({
      native_invoice_count: 6,
    }) as never);
    vi.mocked(paymentHooks.usePayments).mockReturnValue(query([]) as never);
  });

  it("uses customer-scoped authority and exposes related-work population counts", () => {
    render(<MemoryRouter><CustomerOperationsPanel customerId="customer-1" /></MemoryRouter>);

    expect(invoiceHooks.useInvoiceWorkspace).toHaveBeenCalledWith(
      expect.objectContaining({ customerId: "customer-1", limit: 25, offset: 0 }),
      true,
    );
    expect(invoiceHooks.useCustomerBalance).toHaveBeenCalledWith(
      "customer-1",
      expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
      true,
    );
    expect(screen.getByText("Showing 0 of 7 related Jobs.")).toBeInTheDocument();
    expect(screen.getByText("Showing 0 of 4 related Estimates.")).toBeInTheDocument();
    expect(screen.getByText("Showing 0 of 3 Appointments in the operating window · page 1 of 1.")).toBeInTheDocument();
    expect(screen.getByText("Showing 0 of 6 related Invoices · page 1 of 1.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open all related Jobs" })).toHaveAttribute(
      "href",
      "/jobs?customerId=customer-1",
    );
  });

  it("does not claim a bounded Payment receipt page is complete history", () => {
    render(<MemoryRouter><CustomerOperationsPanel customerId="customer-1" /></MemoryRouter>);

    expect(screen.getByText(/does not claim complete Payment history/i)).toBeInTheDocument();
    expect(screen.getByText("No matching Payment receipts are present in the bounded result.")).toBeInTheDocument();
  });

  it("traverses Customer-scoped Appointment and Invoice populations", async () => {
    vi.mocked(schedulingHooks.useAppointments).mockReturnValue(query({
      items: [], total_count: 51, page: 1, page_size: 50,
    }) as never);
    vi.mocked(invoiceHooks.useCustomerBalance).mockReturnValue(query({
      native_invoice_count: 26,
    }) as never);

    render(<MemoryRouter><CustomerOperationsPanel customerId="customer-1" /></MemoryRouter>);
    await userEvent.click(screen.getByRole("button", { name: "Next Appointments" }));
    await userEvent.click(screen.getByRole("button", { name: "Next Invoices" }));

    expect(schedulingHooks.useAppointments).toHaveBeenLastCalledWith(
      expect.objectContaining({ customerId: "customer-1", page: 2, pageSize: 50 }),
      true,
    );
    expect(invoiceHooks.useInvoiceWorkspace).toHaveBeenLastCalledWith(
      expect.objectContaining({ customerId: "customer-1", limit: 25, offset: 25 }),
      true,
    );
  });
});
