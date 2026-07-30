import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as customerHooks from "../../hooks/useCustomers";
import type { CustomerDetail } from "../../types/customers";
import { CustomerDetailView } from "./CustomerDetailView";

vi.mock("../../hooks/useCustomers");

const customer: CustomerDetail = {
  id: "customer-1",
  customer_type: "individual",
  first_name: "Alexandra",
  last_name: "Long-Customer-Name",
  business_name: null,
  primary_phone: "555-0100",
  secondary_phone: null,
  email: "alexandra.with.a.long.address@example.com",
  preferred_contact_method: "email",
  status: "active",
  source: "referral",
  is_vip: false,
  internal_notes: "Authoritative customer context",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
  archived_at: null,
  properties: [],
  contacts: [],
  notes: [],
};

const mutation = (mutate = vi.fn(), isPending = false) => ({
  mutate,
  isPending,
  error: null,
});

describe("CustomerDetailView", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(customerHooks.useCustomerDetail).mockReturnValue({
      isLoading: false,
      isError: false,
      data: customer,
    } as never);
  });

  it("uses the shared accessible confirmation before archiving", async () => {
    const archive = vi.fn();
    vi.mocked(customerHooks.useCustomerMutations).mockReturnValue({
      archive: mutation(archive),
      update: mutation(),
      addNote: mutation(),
      addProperty: mutation(),
      updateProperty: mutation(),
      addContact: mutation(),
      updateContact: mutation(),
    } as never);

    render(<CustomerDetailView customerId={customer.id} onBack={vi.fn()} />);
    expect(
      screen.getByText((content) => content.includes(customer.email as string)),
    ).toHaveClass("break-words");
    await userEvent.click(screen.getByRole("button", { name: "Archive" }));
    expect(
      screen.getByRole("dialog", { name: "Archive this customer?" }),
    ).toBeInTheDocument();
    expect(archive).not.toHaveBeenCalled();
    await userEvent.click(
      screen.getByRole("button", { name: "Archive customer" }),
    );
    expect(archive).toHaveBeenCalledOnce();
  });

  it("classifies a backend failure and retries only when safe", async () => {
    const refetch = vi.fn();
    vi.mocked(customerHooks.useCustomerDetail).mockReturnValue({
      isLoading: false,
      isError: true,
      error: { isAxiosError: true, response: { status: 503 } },
      refetch,
    } as never);
    vi.mocked(customerHooks.useCustomerMutations).mockReturnValue({} as never);

    render(<CustomerDetailView customerId={customer.id} onBack={vi.fn()} />);

    expect(screen.getByText("Service unavailable")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(refetch).toHaveBeenCalledOnce();
  });
});
