import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SalesDemoRoute } from "./SalesDemoRoute";

vi.mock("../auth", () => ({ useAuth: () => ({ refreshAuthorization: vi.fn() }) }));
vi.mock("../hooks/useDemo", () => ({
  useDemoScenarios: () => ({ data: [
    { code: "new_service_call", title: "New Service Call", position: 1, guided_steps: [{ order: 1, action: "Create Customer" }], record_refs: { job_id: "job-1" } },
    { code: "overdue_ar", title: "Overdue AR", position: 5, guided_steps: [{ order: 1, action: "Open Beacon" }], record_refs: { invoice_id: "invoice-1" } },
    { code: "owner_morning_review", title: "Owner Morning Review", position: 8, guided_steps: [{ order: 1, action: "Open Command Center" }], record_refs: {} },
  ] }),
  useResetDemo: () => ({ isPending: false, isSuccess: false, isError: false, mutateAsync: vi.fn() }),
  useDemoFeedback: () => ({ isPending: false, isSuccess: false, mutate: vi.fn() }),
}));

describe.each([[390, "mobile"], [820, "tablet"], [1440, "desktop"]])("Sales Demo at %ipx", (width, label) => {
  beforeEach(() => Object.defineProperty(window, "innerWidth", { value: width, configurable: true }));
  it(`renders guided real-product navigation on ${label}`, () => {
    render(<MemoryRouter><SalesDemoRoute /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Intelligent contractor operations" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Command Center" })).toHaveAttribute("href", "/command-center");
    expect(screen.getByRole("link", { name: "Open Accounting" })).toHaveAttribute("href", "/financial-reports");
    expect(screen.getByRole("link", { name: "Open Dispatch" })).toHaveAttribute("href", "/dispatch");
    expect(screen.getByRole("link", { name: "Open Estimating" })).toHaveAttribute("href", "/estimates");
    expect(screen.getAllByRole("link", { name: "Open evidence" })[0]).toHaveAttribute("href", "/jobs/job-1");
    expect(screen.getAllByRole("link", { name: "Open evidence" })[1]).toHaveAttribute("href", "/invoices/invoice-1");
    expect(screen.getByRole("link", { name: "Open Beacon" })).toHaveAttribute("href", "/command-center");
    expect(screen.getByRole("link", { name: "Open Luminary" })).toHaveAttribute("href", "/luminary");
    expect(screen.getByRole("link", { name: "Open LIA" })).toHaveAttribute("href", "/lia");
    expect(screen.getByRole("button", { name: "Reset Demo Company" })).toBeInTheDocument();
  });
});
