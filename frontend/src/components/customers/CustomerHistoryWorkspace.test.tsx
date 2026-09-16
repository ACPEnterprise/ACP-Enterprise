import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { CustomerHistoryWorkspace } from "./CustomerHistoryWorkspace";
import { buildCustomerHistoryItems } from "./customerHistory";

const job = {
  id: "job-1", job_number: "JOB-1", branch_id: "branch-1", customer_id: "customer-1", customer_display_name: "Customer", service_location_id: "location-1", service_location_label: "10 Main Street", status: "completed", priority: "normal", job_type_code: null, customer_reported_problem_summary: null, appointment_count: 1, earliest_appointment_start_at: null, created_at: "2026-08-01T00:00:00Z", updated_at: "2026-09-01T00:00:00Z", started_at: null, completed_at: "2026-09-01T00:00:00Z", concurrency_version: 1,
} as const;
const appointment = { id: "appointment-1", appointment_number: "APT-1", company_id: "company-1", branch_id: "branch-1", customer_id: "customer-1", service_location_id: "location-1", status: "completed", arrival_window_start_at: "2026-08-31T12:00:00Z", arrival_window_end_at: null, expected_duration_minutes: null, capacity_units: null, concurrency_version: 1, reschedule_count: 0, rescheduled_at: null, cancelled_at: null, cancellation_reason_code: null, created_at: "2026-08-01T00:00:00Z", updated_at: "2026-08-31T12:00:00Z" } as const;
const estimate = { id: "estimate-1", branch_id: "branch-1", customer_id: "customer-1", service_location_id: "location-1", estimate_number: "EST-1", status: "accepted", acceptance_status: "accepted", version: 1, proposal_title: "Repair", currency: "USD", total_amount: "125.00", expires_at: null, updated_at: "2026-08-30T00:00:00Z" } as const;
const invoice = { id: "invoice-1", branch_id: "branch-1", customer_id: "customer-1", customer_number: "C-1", customer_display_name: "Customer", service_location_id: "location-1", service_location_label: "10 Main Street", job_id: "job-1", job_number: "JOB-1", invoice_number: "INV-1", status: "paid", accounting_status: "pending", currency: "USD", issue_date: "2026-09-02", due_date: "2026-09-15", terms: "Due", total_amount: "125.00", open_amount: "0.00", age_days: 0, aging_bucket: "paid", attention_reasons: [] as string[], legacy_evidence_missing: false, version: 1 } as const;
const payment = { id: "payment-1", branch_id: "branch-1", customer_id: "customer-1", intent_id: "intent-1", currency: "USD", status: "settled", captured_amount: "125.00", available_amount: "0.00", applied_amount: "125.00", refunded_amount: "10.00", disputed_amount: "0.00", version: 1, captured_at: "2026-09-03T00:00:00Z" } as const;

const baseProps = {
  customerId: "customer-1",
  locations: [{ id: "location-1", customer_id: "customer-1", address_line_1: "10 Main Street", address_line_2: null, city: "Raleigh", state: "NC", postal_code: "27601", property_type: "single_family", gate_access_instructions: null, water_shutoff_location: null, sewer_septic: null, property_notes: null, is_primary: true, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-09-01T00:00:00Z", archived_at: null }] as const,
  currentJobs: [], historicalJobs: [job], appointments: [appointment], estimates: [estimate], invoices: [invoice], payments: [payment], evidence: [], unavailableDomains: [],
};

describe("CustomerHistoryWorkspace", () => {
  it("orders bounded native history deterministically and labels authority", () => {
    const items = buildCustomerHistoryItems(baseProps);
    expect(items.map((item) => item.id)).toEqual(["payment:payment-1", "invoice:invoice-1", "job:job-1", "appointment:appointment-1", "estimate:estimate-1"]);
    expect(items[0].detail).toContain("USD 10.00 refunded");
    expect(items.every((item) => item.authority.startsWith("Native ACP"))).toBe(true);
  });

  it("presents overview, Location history, limitations, and context-preserving links", () => {
    render(<MemoryRouter><CustomerHistoryWorkspace {...baseProps} /></MemoryRouter>);
    expect(screen.getByRole("region", { name: "Customer history overview" })).toHaveTextContent("Historical Jobs1");
    expect(screen.getByRole("region", { name: "History completeness" })).toHaveTextContent("AttachmentsUNAVAILABLE");
    const locations = screen.getByRole("region", { name: "Service Location history" });
    expect(within(locations).getByText("10 Main Street")).toBeVisible();
    expect(within(locations).getByText(/0 open · 1 historical Jobs · 1 Appointments/)).toBeVisible();
    expect(within(locations).getByRole("link", { name: "View Location Jobs" })).toHaveAttribute("href", "/jobs?customerId=customer-1&serviceLocationId=location-1");
    expect(screen.getByRole("region", { name: "Combined service history" })).toHaveTextContent("Authority: Native ACP Payment evidence");
  });

  it("never turns unavailable domains or empty source history into complete evidence", () => {
    render(<MemoryRouter><CustomerHistoryWorkspace {...baseProps} historicalJobs={[]} appointments={[]} estimates={[]} invoices={[]} payments={[]} unavailableDomains={["Jobs", "Invoices", "Payments"]} /></MemoryRouter>);
    const completeness = screen.getByRole("region", { name: "History completeness" });
    expect(within(completeness).getAllByText("UNAVAILABLE").length).toBeGreaterThanOrEqual(4);
    expect(screen.getByText(/Source-only history may still be unadmitted/)).toBeVisible();
  });
});
