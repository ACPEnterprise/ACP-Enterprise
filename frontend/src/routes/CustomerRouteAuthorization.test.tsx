import { render, screen } from "@testing-library/react";
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
  CustomerDetailView: () => <div>Protected customer detail</div>,
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
    const { unmount } = render(<MemoryRouter><CustomersRoute /></MemoryRouter>);
    expect(screen.getByText("Protected customer list")).toBeInTheDocument();
    unmount();
    render(
      <MemoryRouter initialEntries={["/customers/customer-1"]}>
        <Routes><Route path="/customers/:customerId" element={<CustomerDetailRoute />} /></Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("Protected customer detail")).toBeInTheDocument();
  });
});
