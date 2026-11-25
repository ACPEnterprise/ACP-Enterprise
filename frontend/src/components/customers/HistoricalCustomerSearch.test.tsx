import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { HistoricalCustomerSearch } from "./HistoricalCustomerSearch";

const searchHook = vi.fn();
const historyHook = vi.fn();

vi.mock("../../hooks/useHcpSourceHistory", () => ({
  useHcpHistoricalCustomerSearch: (query: string) => searchHook(query),
  useHcpCustomerSourceHistoryBySource: (sourceId: string | null) => historyHook(sourceId),
}));

describe("HistoricalCustomerSearch", () => {
  beforeEach(() => {
    searchHook.mockReturnValue({ isLoading: false, isError: false, data: undefined });
    historyHook.mockReturnValue({ isLoading: false, isError: false, data: undefined });
  });

  it("searches independently and labels source records as historical only", () => {
    searchHook.mockImplementation((query: string) => ({
      isLoading: false,
      isError: false,
      data: query ? {
        match_count: 1,
        limited: false,
        items: [{
          source_customer_id: "hcp-customer-1",
          display_name: "Richard Example",
          primary_location: "123 Main St, Clearwater, FL 33755",
        }],
      } : undefined,
    }));
    render(<HistoricalCustomerSearch />);

    fireEvent.change(screen.getByLabelText("Search historical customers"), { target: { value: "Richard" } });
    fireEvent.click(screen.getByRole("button", { name: "Search history" }));

    expect(searchHook).toHaveBeenLastCalledWith("Richard");
    expect(screen.getByText("Richard Example")).toBeVisible();
    expect(screen.getByText("HISTORICAL ONLY")).toBeVisible();
    expect(screen.getByText(/not a native Customer record/i)).toBeVisible();
  });

  it("opens a source-backed journey without mutation controls", () => {
    searchHook.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        match_count: 1,
        limited: false,
        items: [{
          source_customer_id: "hcp-customer-1",
          display_name: "Richard Example",
          primary_location: "123 Main St",
        }],
      },
    });
    historyHook.mockImplementation((sourceId: string | null) => ({
      isLoading: false,
      isError: false,
      data: sourceId ? {
        source_customer_id: sourceId,
        source_manifest_sha256: "a".repeat(64),
        counts: { locations: 1, jobs: 4, appointments: 3, estimates: 2, invoices: 2, payments: 1, refunds: 0 },
        locations: [{ source_id: "location-1", address: "123 Main St", city: "Clearwater", state: "FL", postal_code: "33755" }],
        jobs: [{ source_id: "job-1", source_location_id: null, number: "J-100", status: "completed", assigned_employee_source_ids: [] }],
        appointments: [{ source_id: "appointment-1", source_job_id: "job-1", scheduled_start: "2026-01-01T12:00:00Z", assigned_employee_source_ids: [] }],
        estimates: [{ source_id: "estimate-1", number: "E-100", status: "approved", options: [] }],
        invoices: [{ source_id: "invoice-1", source_job_id: "job-1", number: "I-100", status: "paid", payments: [{ source_id: "payment-1", status: "succeeded", amount_cents: 12500, overlap_disposition: "HCP_ONLY_SOURCE_EVIDENCE" }], refunds: [] }],
      } : undefined,
    }));
    render(<HistoricalCustomerSearch />);
    fireEvent.click(screen.getByRole("button", { name: /Richard Example/ }));

    const journey = screen.getByRole("region", { name: "Historical customer journey" });
    expect(within(journey).getByText("SOURCE BACKED")).toBeVisible();
    expect(within(journey).getByText("123 Main St")).toBeVisible();
    expect(within(journey).getByText("4")).toBeVisible();
    expect(within(journey).getByText("Job J-100")).toBeVisible();
    expect(within(journey).getByText(/Held relationship: source Location unavailable/)).toBeVisible();
    expect(within(journey).getByText("Invoice I-100")).toBeVisible();
    expect(within(journey).getByText(/Payment payment-1/)).toBeVisible();
    expect(screen.queryByRole("button", { name: /edit|admit|import|create/i })).not.toBeInTheDocument();
  });
});
