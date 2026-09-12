import { render, screen } from "@testing-library/react";
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

describe("Customer operations reliability", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(jobHooks.useJobs).mockReturnValue(query({
      items: [], total_count: 0, page: 1, page_size: 25, total_pages: 0,
    }) as never);
    vi.mocked(schedulingHooks.useAppointments).mockReturnValue(query({
      items: [], total_count: 0, page: 1, page_size: 50,
    }) as never);
    vi.mocked(estimateHooks.useEstimates).mockReturnValue(query({ items: [], total: 0 }) as never);
    vi.mocked(invoiceHooks.useInvoices).mockReturnValue(query([]) as never);
    vi.mocked(paymentHooks.usePayments).mockReturnValue(query([]) as never);
  });

  it("shows a truthful no-current-Job fixture without hiding the Customer", () => {
    render(<MemoryRouter><CustomerOperationsPanel customerId="customer-no-job" /></MemoryRouter>);

    expect(jobHooks.useJobs).toHaveBeenCalledWith(
      expect.objectContaining({ customerId: "customer-no-job" }),
      true,
    );
    expect(screen.getByText("No Jobs are currently linked in native Job authority.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Operational workspace" })).toBeInTheDocument();
  });

  it("keeps partial related-work failure separate from Customer identity", () => {
    vi.mocked(schedulingHooks.useAppointments).mockReturnValue({
      isLoading: false,
      isError: true,
      isSuccess: false,
      error: { isAxiosError: true, response: { status: 503 } },
    } as never);

    render(<MemoryRouter><CustomerOperationsPanel customerId="customer-partial" /></MemoryRouter>);

    expect(screen.getByText(/Some related work is unavailable/)).toBeInTheDocument();
    expect(screen.getByText(/Customer identity remains available/)).toBeInTheDocument();
  });
});
