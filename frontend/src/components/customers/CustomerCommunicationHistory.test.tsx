import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as communicationsApi from "../../api/communications";
import { CustomerCommunicationHistory } from "./CustomerCommunicationHistory";

vi.mock("../../api/communications");

describe("CustomerCommunicationHistory", () => {
  it("shows scoped delivery evidence without mutation controls", async () => {
    vi.mocked(communicationsApi.listCustomerCommunicationHistory).mockResolvedValue([{
      id: "communication-1", communication_type: "appointment_reminder",
      channel: "sms", customer_id: "customer-1", contact_id: "contact-1",
      recipient_display: "SMS ending in 0123", state: "failed", retry_count: 2,
      terminal_failure: true, scheduled_at: "2026-08-30T12:00:00Z",
      sent_at: null, failed_at: "2026-08-30T12:05:00Z",
      error_code: "provider_rejected", error_category: "terminal",
      created_at: "2026-08-30T11:59:00Z",
    }]);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><CustomerCommunicationHistory customerId="customer-1" /></QueryClientProvider>);

    expect(await screen.findByText("appointment reminder")).toBeInTheDocument();
    expect(screen.getByText("Needs attention")).toBeInTheDocument();
    expect(screen.getByText(/will not retry automatically/)).toBeInTheDocument();
    expect(screen.getByText(/SMS ending in 0123/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(communicationsApi.listCustomerCommunicationHistory).toHaveBeenCalledWith("customer-1");
  });

  it("does not reflect protected provider details from a failed history request", async () => {
    vi.mocked(communicationsApi.listCustomerCommunicationHistory).mockRejectedValue({
      isAxiosError: true,
      response: {
        status: 503,
        data: { detail: "/srv/provider/customer-communication-secret-canary" },
      },
    });
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <CustomerCommunicationHistory customerId="customer-1" />
      </QueryClientProvider>,
    );

    expect(
      await screen.findByText("The service could not be reached. Try again."),
    ).toBeVisible();
    expect(screen.queryByText(/communication-secret-canary/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\/srv\/provider/)).not.toBeInTheDocument();
  });

  it("keeps provider acceptance distinct from confirmed delivery and hides private details", async () => {
    vi.mocked(communicationsApi.listCustomerCommunicationHistory).mockResolvedValue([{
      id: "communication-accepted", communication_type: "technician_en_route",
      channel: "sms", customer_id: "customer-1", contact_id: "contact-1",
      recipient_display: "SMS ending in 0123", state: "accepted", retry_count: 0,
      terminal_failure: false, scheduled_at: "2026-08-30T12:00:00Z",
      sent_at: null, failed_at: null, error_code: "sql-provider-secret-canary",
      error_category: "provider_internal_canary", created_at: "2026-08-30T11:59:00Z",
    }]);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><CustomerCommunicationHistory customerId="customer-1" /></QueryClientProvider>);

    expect(await screen.findByText("Pending delivery")).toBeInTheDocument();
    expect(screen.getByText(/accepted this message/)).toBeInTheDocument();
    expect(screen.queryByText("Delivered")).not.toBeInTheDocument();
    expect(screen.queryByText(/sql-provider-secret-canary/)).not.toBeInTheDocument();
    expect(screen.queryByText(/provider_internal_canary/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\+15555550123/)).not.toBeInTheDocument();
  });

  it("announces loading and shows a truthful empty state", async () => {
    let resolveHistory: (value: []) => void = () => undefined;
    vi.mocked(communicationsApi.listCustomerCommunicationHistory).mockReturnValue(
      new Promise<[]>((resolve) => { resolveHistory = resolve; }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><CustomerCommunicationHistory customerId="customer-1" /></QueryClientProvider>);

    expect(screen.getByLabelText("Loading communication history")).toBeInTheDocument();
    resolveHistory([]);
    expect(await screen.findByText(/No communication requests have been recorded/)).toBeInTheDocument();
  });
});
