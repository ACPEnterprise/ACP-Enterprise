import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RevenueCycleRoute } from "./RevenueCycleRoute";

const permission = vi.fn();
vi.mock("../auth", () => ({ useHasPermission: (code: string) => permission(code) }));
vi.mock("../hooks/useJobs", () => ({ useJobs: () => ({ isPending: false, isError: false, data: { items: [
  { id: "job-ready", job_number: "J-1", customer_display_name: "Ready Customer", status: "ready", appointment_count: 0 },
  { id: "job-complete", job_number: "J-2", customer_display_name: "Done Customer", status: "completed", appointment_count: 1 },
] } }) }));
vi.mock("../hooks/useEstimates", () => ({ useEstimates: () => ({ isPending: false, data: { items: [{ id: "est-1", status: "sent", converted_job_id: null }, { id: "est-2", status: "approved", converted_job_id: null }] } }) }));
vi.mock("../hooks/useInvoices", () => ({ useInvoices: () => ({ isPending: false, data: [{ id: "inv-1", job_id: "another-job", status: "issued", open_amount: "50.00", accounting_status: "pending" }] }) }));
vi.mock("../hooks/usePayments", () => ({ usePayments: () => ({ isPending: false, data: [{ id: "pay-1" }] }) }));

describe("RevenueCycleRoute", () => {
  beforeEach(() => permission.mockReturnValue(true));

  it("composes explicit operational queues without financial ranking", () => {
    render(<MemoryRouter><RevenueCycleRoute /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Revenue cycle" })).toBeVisible();
    expect(screen.getByText("Completed not invoiced").nextElementSibling).toHaveTextContent("1");
    expect(screen.getByText("Accepted not converted").nextElementSibling).toHaveTextContent("1");
    expect(screen.getByText("J-2")).toBeVisible();
    expect(screen.getByText(/Amounts never influence queue priority/)).toBeVisible();
  });

  it("requires Job read authority", () => {
    permission.mockImplementation((code: string) => code !== "COMPANY_JOB_READ");
    render(<MemoryRouter><RevenueCycleRoute /></MemoryRouter>);
    expect(screen.getByText("You are not authorized to view the operational revenue cycle.")).toBeVisible();
  });
});
