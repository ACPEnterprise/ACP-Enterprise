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
      recipient: "+15555550123", state: "failed", retry_count: 2,
      terminal_failure: true, scheduled_at: "2026-08-30T12:00:00Z",
      sent_at: null, failed_at: "2026-08-30T12:05:00Z",
      error_code: "provider_rejected", error_category: "terminal",
      created_at: "2026-08-30T11:59:00Z",
    }]);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><CustomerCommunicationHistory customerId="customer-1" /></QueryClientProvider>);

    expect(await screen.findByText("appointment reminder")).toBeInTheDocument();
    expect(screen.getByText(/Terminal delivery failure/)).toBeInTheDocument();
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
});
