import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CustomersRoute } from "./CustomersRoute";

const { useHasPermission } = vi.hoisted(() => ({ useHasPermission: vi.fn() }));
vi.mock("../auth", () => ({ useHasPermission }));
vi.mock("../components/customers/CustomerManagement", () => ({
  CustomerManagement: () => <div>Customer management workspace</div>,
}));

describe("CustomersRoute", () => {
  it("keeps the customer import workspace behind customer-read permission", () => {
    useHasPermission.mockReturnValue(true);
    render(<CustomersRoute />);
    expect(screen.getByText("Customer management workspace")).toBeInTheDocument();
  });

  it("does not expose import or roster UI without customer-read permission", () => {
    useHasPermission.mockReturnValue(false);
    render(<CustomersRoute />);
    expect(screen.getByText("You are not authorized to view Customers.")).toBeInTheDocument();
    expect(screen.queryByText("Customer management workspace")).not.toBeInTheDocument();
  });
});
