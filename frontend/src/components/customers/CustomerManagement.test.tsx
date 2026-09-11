import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as customerHooks from "../../hooks/useCustomers";
import * as administrationHooks from "../../features/administration/hooks";
import { CustomerManagement } from "./CustomerManagement";

vi.mock("../../hooks/useCustomers");
vi.mock("../../features/administration/hooks");
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
    vi.mocked(administrationHooks.useMigrationReadiness).mockReturnValue({ isLoading: false, isError: false, data: undefined } as never);
    vi.mocked(customerHooks.useCustomerMutations).mockReturnValue({
      create: mutation,
      duplicateCheck: mutation,
    } as never);
  });

  it("renders phone-safe customer links to durable detail routes", () => {
    vi.mocked(customerHooks.useCustomerSearch).mockReturnValue({
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
        total_count: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
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
    vi.mocked(customerHooks.useCustomerSearch).mockReturnValue({
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
    vi.mocked(customerHooks.useCustomerSearch).mockReturnValue({
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
        total_count: 1, page: 1, page_size: 20, total_pages: 1,
      },
    } as never);

    render(
      <MemoryRouter>
        <CustomerManagement />
      </MemoryRouter>,
    );

    expect(screen.getByText(/business · unknown/)).toBeInTheDocument();
  });

  it("keeps authorized customer evidence visible without exposing manage controls", () => {
    permissions.clear();
    permissions.add("COMPANY_CUSTOMER_READ");
    vi.mocked(customerHooks.useCustomerSearch).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        items: [{
          id: "customer-1", customer_type: "individual", first_name: "Alex",
          last_name: "Rivera", business_name: null, primary_phone: "555-0100",
          email: null, status: "active", source: "referral", is_vip: false,
        }],
        total_count: 1, page: 1, page_size: 20, total_pages: 1,
      },
    } as never);

    render(<MemoryRouter><CustomerManagement /></MemoryRouter>);

    expect(screen.getByRole("link", { name: /Alex Rivera/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New customer" })).not.toBeInTheDocument();
  });

  it("does not claim an empty upstream source when no native records are admitted", () => {
    vi.mocked(customerHooks.useCustomerSearch).mockReturnValue({
      isLoading: false, isError: false,
      data: { items: [], total_count: 0, page: 1, page_size: 20, total_pages: 0 },
    } as never);

    render(<MemoryRouter><CustomerManagement /></MemoryRouter>);

    expect(screen.getByText("No Customer records are currently admitted.")).toBeInTheDocument();
    expect(screen.getByText(/not proof that upstream source data is empty or complete/i)).toBeInTheDocument();
  });

  it("recovers safely when a changed result set leaves the current page empty", () => {
    vi.mocked(customerHooks.useCustomerSearch).mockReturnValue({
      isLoading: false, isError: false,
      data: { items: [], total_count: 21, page: 2, page_size: 20, total_pages: 2 },
    } as never);

    render(<MemoryRouter><CustomerManagement /></MemoryRouter>);

    expect(screen.getByText("This roster page is no longer available.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Return to first page" })).toBeInTheDocument();
  });

  it("keeps held source records distinct from admitted Customers and shows the source date", () => {
    permissions.add("COMPANY_ADMINISTER");
    vi.mocked(administrationHooks.useMigrationReadiness).mockReturnValue({
      isLoading: false, isError: false,
      data: { overall_status: "PARTIAL", stale: false, historical_window: { ends_on: "2026-09-10" }, counts: [{ domain: "Customers", source: 100, migrated: 90, held: 5, exception: 3, non_applicable: 0, deferred: 1, unresolved: 1, delta: 0 }] },
    } as never);
    vi.mocked(customerHooks.useCustomerSearch).mockReturnValue({ isLoading: false, isError: false, data: { items: [], total_count: 0, page: 1, page_size: 20, total_pages: 0 } } as never);

    render(<MemoryRouter><CustomerManagement /></MemoryRouter>);

    expect(screen.getByText(/Source evidence through 2026-09-10/)).toBeInTheDocument();
    expect(screen.getByText("90 admitted / 100 source")).toBeInTheDocument();
    expect(screen.getByText(/5 held · 3 exception · 1 unresolved · delta 0/)).toBeInTheDocument();
    expect(screen.getByText(/never presented as native Customers/)).toBeInTheDocument();
  });
});
