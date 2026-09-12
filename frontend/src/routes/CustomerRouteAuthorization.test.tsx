import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CustomerDetailRoute } from "./CustomerDetailRoute";
import { CustomersRoute } from "./CustomersRoute";

const permissions = new Set<string>();
vi.mock("../auth", () => ({
  useHasPermission: (code: string) => permissions.has(code),
}));
vi.mock("../components/customers/CustomerManagement", () => ({
  CustomerManagement: () => <div>Protected customer list</div>,
}));
vi.mock("../components/customers/CustomerDetailView", () => ({
  CustomerDetailView: ({ onBack }: { onBack: () => void }) => <div>Protected customer detail<button onClick={onBack}>Back from customer</button></div>,
}));

describe("Customer route authorization", () => {
  beforeEach(() => permissions.clear());

  it("does not mount customer list queries without Customer read", () => {
    render(<MemoryRouter><CustomersRoute /></MemoryRouter>);
    expect(screen.getByText(/not authorized to view Customers/i)).toBeInTheDocument();
    expect(screen.queryByText("Protected customer list")).not.toBeInTheDocument();
  });

  it("does not mount customer detail queries without Customer read", () => {
    render(
      <MemoryRouter initialEntries={["/customers/customer-1"]}>
        <Routes><Route path="/customers/:customerId" element={<CustomerDetailRoute />} /></Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText(/not authorized to view this Customer/i)).toBeInTheDocument();
    expect(screen.queryByText("Protected customer detail")).not.toBeInTheDocument();
  });

  it("mounts authorized customer surfaces", () => {
    permissions.add("COMPANY_CUSTOMER_READ");
    permissions.add("COMPANY_JOB_READ");
    const { unmount } = render(<MemoryRouter><CustomersRoute /></MemoryRouter>);
    expect(screen.getByText("Protected customer list")).toBeInTheDocument();
    unmount();
    render(
      <MemoryRouter initialEntries={["/customers/customer-1"]}>
        <Routes><Route path="/customers/:customerId" element={<CustomerDetailRoute />} /></Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("Protected customer detail")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Ask LIA about this Customer" }),
    ).toBeVisible();
  });

  it("returns a calendar-opened Customer to the validated Scheduling scope", async () => {
    permissions.add("COMPANY_CUSTOMER_READ");
    render(
      <MemoryRouter initialEntries={["/customers/customer-1?returnTo=%2Fscheduling%3Fdate%3D2026-08-13%26view%3Dmonth"]}>
        <Routes>
          <Route path="/customers/:customerId" element={<CustomerDetailRoute />} />
          <Route path="/scheduling" element={<div>Restored schedule</div>} />
        </Routes>
      </MemoryRouter>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Back from customer" }));
    expect(screen.getByText("Restored schedule")).toBeVisible();
  });
});
