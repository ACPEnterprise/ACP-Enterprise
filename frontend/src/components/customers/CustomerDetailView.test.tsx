import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as customerHooks from "../../hooks/useCustomers";
import type { CustomerDetail } from "../../types/customers";
import { CustomerDetailView } from "./CustomerDetailView";

vi.mock("../../hooks/useCustomers");
vi.mock("./CustomerOperationsPanel", () => ({
  CustomerOperationsPanel: () => <div>Customer operational workspace</div>,
}));

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
    vi.mocked(customerHooks.useCustomerConsents).mockReturnValue({
      isError: false,
      isSuccess: true,
      data: [],
    } as never);
    vi.mocked(customerHooks.useCustomerTimeline).mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: {
        items: [{
          id: "event-1", timestamp: "2026-08-07T12:00:00Z",
          event_type: "customer.created", actor: null,
          entity: { type: "customer", id: customer.id },
          summary: "Customer created", metadata: {}, branch_id: "branch-1",
          company_id: "company-1", customer_id: customer.id,
          correlation_id: "correlation-1",
        }],
        page: 1, page_size: 50, total_count: 1, total_pages: 1,
      },
    } as never);
  });

  it("uses the shared accessible confirmation before archiving", async () => {
    const archive = vi.fn();
    vi.mocked(customerHooks.useCustomerMutations).mockReturnValue({
      archive: mutation(archive),
      restore: mutation(),
      update: mutation(),
      addNote: mutation(),
      recordConsent: mutation(),
      duplicateCheck: mutation(),
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

  it("renders an adapted current-contract location with unknown legacy facts", () => {
    vi.mocked(customerHooks.useCustomerDetail).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        ...customer,
        customer_type: "residential",
        business_name: "Preview Customer",
        properties: [
          {
            id: "location-1",
            customer_id: customer.id,
            address_line_1: "10 Preview Street",
            address_line_2: null,
            city: "Albany",
            state: "NY",
            postal_code: "12207",
            property_type: "unknown",
            gate_access_instructions: null,
            water_shutoff_location: null,
            sewer_septic: "unknown",
            property_notes: null,
            is_primary: false,
            created_at: "2026-08-01T12:00:00Z",
            updated_at: "2026-08-01T12:00:00Z",
            archived_at: null,
          },
        ],
      },
    } as never);
    vi.mocked(customerHooks.useCustomerMutations).mockReturnValue({
      archive: mutation(),
      restore: mutation(),
      update: mutation(),
      addNote: mutation(),
      recordConsent: mutation(),
      duplicateCheck: mutation(),
      addProperty: mutation(),
      updateProperty: mutation(),
      addContact: mutation(),
      updateContact: mutation(),
    } as never);

    render(<CustomerDetailView customerId={customer.id} onBack={vi.fn()} />);

    expect(screen.getByText("Preview Customer")).toBeInTheDocument();
    expect(screen.getByText("10 Preview Street")).toBeInTheDocument();
    expect(screen.getByText("unknown · unknown")).toBeInTheDocument();
  });

  it("records explicit consent and renders consent-safe history", async () => {
    const recordConsent = vi.fn();
    vi.mocked(customerHooks.useCustomerConsents).mockReturnValue({
      isError: false,
      isSuccess: true,
      data: [
        {
          id: "consent-1",
          customer_id: customer.id,
          channel: "sms",
          decision: "withdrawn",
          source: "customer_request",
          reason: null,
          recorded_at: "2026-08-07T12:00:00Z",
          recorded_by_user_id: "user-1",
          branch_id: "branch-1",
        },
      ],
    } as never);
    vi.mocked(customerHooks.useCustomerMutations).mockReturnValue({
      archive: mutation(), update: mutation(), addNote: mutation(),
      restore: mutation(),
      recordConsent: mutation(recordConsent), addProperty: mutation(),
      duplicateCheck: mutation(),
      updateProperty: mutation(), addContact: mutation(), updateContact: mutation(),
    } as never);

    render(<CustomerDetailView customerId={customer.id} onBack={vi.fn()} />);
    expect(screen.getByText("SMS")).toBeInTheDocument();
    expect(screen.getByText(/withdrawn/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Record consent" }));
    expect(recordConsent).toHaveBeenCalledWith({
      channel: "sms",
      decision: "granted",
      source: "staff_confirmed",
      reason: null,
    });
    expect(screen.getByText("Customer created")).toBeInTheDocument();
    expect(screen.getByText("Recorded preference unavailable")).toBeInTheDocument();
  });

  it("restores archived evidence without rewriting history", async () => {
    const restore = vi.fn();
    vi.mocked(customerHooks.useCustomerDetail).mockReturnValue({
      isLoading: false, isError: false,
      data: { ...customer, archived_at: "2026-08-08T12:00:00Z" },
    } as never);
    vi.mocked(customerHooks.useCustomerMutations).mockReturnValue({
      archive: mutation(), restore: mutation(restore), update: mutation(),
      addNote: mutation(), recordConsent: mutation(), addProperty: mutation(),
      duplicateCheck: mutation(),
      updateProperty: mutation(), addContact: mutation(), updateContact: mutation(),
    } as never);

    render(<CustomerDetailView customerId={customer.id} onBack={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Restore customer" }));
    expect(restore).toHaveBeenCalledOnce();
    expect(screen.queryByRole("button", { name: "Archive" })).not.toBeInTheDocument();
  });

  it("reviews duplicate evidence without offering an unsafe merge", async () => {
    const duplicateCheck = vi.fn((_input, options) => options.onSuccess([{
      ...customer, id: "candidate-2", reasons: ["matching_normalized_email"],
    }]));
    vi.mocked(customerHooks.useCustomerMutations).mockReturnValue({
      archive: mutation(), restore: mutation(), update: mutation(), addNote: mutation(),
      recordConsent: mutation(), duplicateCheck: mutation(duplicateCheck),
      addProperty: mutation(), updateProperty: mutation(), addContact: mutation(),
      updateContact: mutation(),
    } as never);

    render(<CustomerDetailView customerId={customer.id} onBack={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Check for possible duplicates" }));
    expect(duplicateCheck).toHaveBeenCalledOnce();
    expect(screen.getByText("matching normalized email")).toBeInTheDocument();
    expect(screen.getByText(/Native consolidation authority is not available/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /merge/i })).not.toBeInTheDocument();
  });
});
