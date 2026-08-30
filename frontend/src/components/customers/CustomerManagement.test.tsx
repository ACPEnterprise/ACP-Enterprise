import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as customerHooks from "../../hooks/useCustomers";
import { CustomerManagement } from "./CustomerManagement";

vi.mock("../../hooks/useCustomers");
const permissions = new Set<string>();
vi.mock("../../auth", () => ({
  useHasPermission: (code: string) => permissions.has(code),
}));

const mutation = {
  mutate: vi.fn(),
  isPending: false,
  error: null,
};

describe("CustomerManagement", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    permissions.clear();
    permissions.add("COMPANY_CUSTOMER_MANAGE");
    vi.mocked(customerHooks.useCustomerMutations).mockReturnValue({
      create: mutation,
      duplicateCheck: mutation,
    } as never);
  });

  it("renders phone-safe customer links to durable detail routes", () => {
    vi.mocked(customerHooks.useCustomerList).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        items: [
          {
            id: "customer-1",
            customer_type: "individual",
            first_name: "Alex",
            last_name: "Rivera",
            business_name: null,
            primary_phone: "555-0100",
            secondary_phone: null,
            email: "alex@example.com",
            preferred_contact_method: "phone",
            status: "active",
            source: "referral",
            is_vip: false,
            internal_notes: null,
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
            archived_at: null,
          },
        ],
        total: 1,
        limit: 20,
        offset: 0,
      },
    } as never);

    render(
      <MemoryRouter>
        <CustomerManagement />
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: /Alex Rivera/ })).toHaveAttribute(
      "href",
      "/customers/customer-1",
    );
  });

  it("distinguishes authentication failure from an empty customer list", () => {
    vi.mocked(customerHooks.useCustomerList).mockReturnValue({
      isLoading: false,
      isError: true,
      error: { isAxiosError: true, response: { status: 401 } },
    } as never);

    render(
      <MemoryRouter>
        <CustomerManagement />
      </MemoryRouter>,
    );

    expect(screen.getByText("Authentication required")).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "No customers yet." }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("renders a safe source label when a migrated response contains null", () => {
    vi.mocked(customerHooks.useCustomerList).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        items: [
          {
            id: "customer-null-source",
            customer_type: "business",
            first_name: null,
            last_name: null,
            business_name: "Legacy Customer",
            primary_phone: "555-0101",
            email: null,
            status: "active",
            source: null,
            is_vip: false,
          },
        ],
        total: 1,
      },
    } as never);

    render(
      <MemoryRouter>
        <CustomerManagement />
      </MemoryRouter>,
    );

    expect(screen.getByText("business · unknown")).toBeInTheDocument();
  });

  it("keeps authorized customer evidence visible without exposing manage controls", () => {
    permissions.clear();
    permissions.add("COMPANY_CUSTOMER_READ");
    vi.mocked(customerHooks.useCustomerList).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        items: [{
          id: "customer-1", customer_type: "individual", first_name: "Alex",
          last_name: "Rivera", business_name: null, primary_phone: "555-0100",
          email: null, status: "active", source: "referral", is_vip: false,
        }],
        total: 1,
      },
    } as never);

    render(<MemoryRouter><CustomerManagement /></MemoryRouter>);

    expect(screen.getByRole("link", { name: /Alex Rivera/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New customer" })).not.toBeInTheDocument();
  });
});
