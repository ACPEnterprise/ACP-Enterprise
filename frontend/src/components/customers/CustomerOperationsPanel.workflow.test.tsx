import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as auth from "../../auth";
import * as estimateHooks from "../../hooks/useEstimates";
import * as invoiceHooks from "../../hooks/useInvoices";
import * as sourceHistoryHooks from "../../hooks/useHcpSourceHistory";
import * as jobHooks from "../../hooks/useJobs";
import * as paymentHooks from "../../hooks/usePayments";
import * as schedulingHooks from "../../hooks/useScheduling";
import { CustomerOperationsPanel } from "./CustomerOperationsPanel";

vi.mock("../../auth");
vi.mock("../../hooks/useEstimates");
vi.mock("../../hooks/useInvoices");
vi.mock("../../hooks/useHcpSourceHistory");
vi.mock("../../hooks/useJobs");
vi.mock("../../hooks/usePayments");
vi.mock("../../hooks/useScheduling");

const query = (data: unknown) => ({ data, isLoading: false, isError: false, isSuccess: true });
const job = (id: string, status: string, appointmentCount = 0) => ({ id, job_number: id.toUpperCase(), status, appointment_count: appointmentCount, service_location_id: "location-1", service_location_label: "10 Main Street", created_at: "2026-09-11T00:00:00Z", completed_at: status === "completed" ? "2026-09-12T00:00:00Z" : null, updated_at: "2026-09-12T00:00:00Z" });

describe("CustomerOperationsPanel office workflow", () => {
  beforeEach(() => {
    vi.mocked(auth.useHasPermission).mockReturnValue(true);
    vi.mocked(jobHooks.useJobs).mockImplementation((filters) => query(filters.status?.includes("completed")
      ? { items: [job("job-history", "completed", 1)], total_count: 1 }
      : { items: [job("job-current", "ready")], total_count: 1 }) as never);
    vi.mocked(schedulingHooks.useAppointments).mockReturnValue(query({ items: [{ id: "appointment-1", appointment_number: "APT-1", customer_id: "customer-1", service_location_id: "location-1", arrival_window_start_at: "2026-09-12T14:00:00Z", updated_at: "2026-09-12T00:00:00Z", status: "scheduled" }] }) as never);
    vi.mocked(estimateHooks.useEstimates).mockReturnValue(query({ items: [{ id: "estimate-1", estimate_number: "EST-1", service_location_id: "location-1", proposal_title: "Repair", currency: "USD", total_amount: "125.00", updated_at: "2026-09-12T00:00:00Z", status: "approved" }] }) as never);
    vi.mocked(invoiceHooks.useInvoiceWorkspace).mockReturnValue(query([{ id: "invoice-1", invoice_number: "INV-1", service_location_id: "location-1", currency: "USD", total_amount: "100.00", open_amount: "75.00", issue_date: "2026-09-12", status: "partially_paid" }, { id: "invoice-paid", invoice_number: "INV-PAID", service_location_id: "location-1", currency: "USD", total_amount: "50.00", open_amount: "0.00", issue_date: "2026-09-11", status: "paid" }]) as never);
    vi.mocked(invoiceHooks.useCustomerBalance).mockReturnValue(query({ currency: "USD", open_balance: "75.00", native_invoice_count: 2, applied_payment_total: "25.00", unapplied_receipt_total: "10.00", legacy_evidence_incomplete: false, as_of: "2026-09-12", evidence_classifications: [{ company_id: "company-1", customer_id: "customer-1", source_system: "acp_native", source_record_identity: "customer-1", as_of: "2026-09-12", acquired_at: "2026-09-12T00:00:00Z", evidence_digest: "a", completeness: "complete", conflict_state: "none", classification: "CURRENT_AUTHORITATIVE", authority: "native_invoice_and_receipt_authority" }] }) as never);
    vi.mocked(paymentHooks.usePayments).mockReturnValue(query([{ id: "receipt-1", customer_id: "customer-1", currency: "USD", status: "partially_applied", captured_amount: "35.00", applied_amount: "25.00", available_amount: "10.00", refunded_amount: "0.00", captured_at: "2026-09-12T00:00:00Z" }]) as never);
    vi.mocked(sourceHistoryHooks.useHcpCustomerSourceHistory).mockReturnValue(
      query(undefined) as never,
    );
  });

  it("shows exact HCP history without promoting QuickBooks overlap to native Accounting", () => {
    vi.mocked(sourceHistoryHooks.useHcpCustomerSourceHistory).mockReturnValue(query({
      contract: "hcp-customer-source-history/v2",
      authority: "HCP_SOURCE_BACKED_OPERATIONAL_HISTORY",
      accepted_as_acp_accounting: false,
      mutation_authority: "none",
      source_customer_id: "source-customer-1",
      source_manifest_sha256: "digest",
      counts: { estimates: 1, invoices: 1, payments: 1, refunds: 1 },
      estimates: [{ source_id: "estimate-source-1", number: "100", status: "approved", created_at: null, updated_at: null, options: [], authority: "HCP_SOURCE_BACKED_OPERATIONAL_HISTORY" }],
      invoices: [{ source_id: "invoice-source-1", source_job_id: "job-source-1", number: "200", status: "paid", amount_cents: 12500, balance_cents: 0, invoice_date: null, service_date: null, authority: "HCP_SOURCE_BACKED_OPERATIONAL_HISTORY", payments: [{ source_id: "payment-source-1", status: "succeeded", amount_cents: 12500, date: null, payment_method: "imported_from_quickbooks", overlap_disposition: "HOLD_FROM_AGGREGATION_PENDING_QBO_RECONCILIATION", authority: "HCP_SOURCE_BACKED_PAYMENT_EVIDENCE_NOT_ACCOUNTING_POSTING" }], refunds: [{ source_id: null, status: "succeeded", amount_cents: 2500, date: null, payment_method: "card", identity_disposition: "SOURCE_BACKED_UNLINKED_REFUND", aggregation_safe: false, authority: "HCP_SOURCE_BACKED_REFUND_EVIDENCE_NOT_ACCOUNTING_POSTING" }] }],
    }) as never);

    render(<MemoryRouter><CustomerOperationsPanel customerId="customer-1" locations={[]} /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Housecall Pro history" })).toBeInTheDocument();
    expect(screen.getByText("Source-backed evidence")).toBeVisible();
    expect(screen.getByText(/not ACP Accounting postings/i)).toBeVisible();
    expect(screen.getByText(/held from aggregation/i)).toBeVisible();
    expect(screen.queryByText("source-customer-1")).not.toBeInTheDocument();
  });

  it("separates current and historical work and preserves action context", () => {
    render(<MemoryRouter><CustomerOperationsPanel customerId="customer-1" locations={[]} /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Current Jobs" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Historical Jobs" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Create Job" })).toHaveAttribute("href", "/jobs?create=1&customerId=customer-1");
    expect(screen.getByRole("link", { name: "Open Job to schedule" })).toHaveAttribute("href", "/jobs/job-current?returnTo=%2Fcustomers%2Fcustomer-1");
    expect(screen.getAllByRole("link", { name: /APT-1/ }).every((item) => item.getAttribute("href") === "/appointments/appointment-1")).toBe(true);
    expect(screen.getAllByRole("link", { name: /INV-1/ }).every((item) => item.getAttribute("href") === "/invoices/invoice-1")).toBe(true);
    expect(screen.getAllByRole("link", { name: /INV-PAID/ }).every((item) => item.getAttribute("href") === "/invoices/invoice-paid")).toBe(true);
    expect(screen.getByRole("link", { name: "Open Invoice / AR workspace" })).toHaveAttribute("href", "/invoices?customerId=customer-1");
    expect(screen.getAllByRole("link", { name: /USD 35.00/ }).every((item) => item.getAttribute("href") === "/payments/receipt-1")).toBe(true);
    expect(paymentHooks.usePayments).toHaveBeenCalledWith(true, "customer-1");
    expect(screen.getAllByText("USD 75.00").length).toBeGreaterThan(0);
  });

  it("does not turn absent related evidence into fabricated relationships or zero", () => {
    vi.mocked(jobHooks.useJobs).mockReturnValue(query({ items: [], total_count: 0 }) as never);
    vi.mocked(schedulingHooks.useAppointments).mockReturnValue(query({ items: [] }) as never);
    vi.mocked(estimateHooks.useEstimates).mockReturnValue(query({ items: [] }) as never);
    vi.mocked(invoiceHooks.useInvoiceWorkspace).mockReturnValue(query([]) as never);
    vi.mocked(invoiceHooks.useCustomerBalance).mockReturnValue({ data: undefined, isLoading: false, isError: false, isSuccess: true } as never);
    vi.mocked(paymentHooks.usePayments).mockReturnValue(query([]) as never);
    render(<MemoryRouter><CustomerOperationsPanel customerId="customer-1" locations={[]} /></MemoryRouter>);
    expect(screen.getByText("No current Jobs are linked in native Job authority.")).toBeInTheDocument();
    expect(screen.getByText("No historical Jobs are present in native Job authority.")).toBeInTheDocument();
    expect(screen.getByText(/Balance evidence unavailable/)).toBeInTheDocument();
    expect(screen.getByText(/does not imply that unavailable source history is zero/)).toBeInTheDocument();
  });

  it("marks the workspace partial when an owning domain is unavailable", () => {
    vi.mocked(estimateHooks.useEstimates).mockReturnValue({ data: undefined, isLoading: false, isError: true, isSuccess: false } as never);
    render(<MemoryRouter><CustomerOperationsPanel customerId="customer-1" locations={[]} /></MemoryRouter>);
    expect(screen.getByText("Related work is partial")).toBeInTheDocument();
    expect(screen.getByText(/do not treat missing sections or amounts as complete/i)).toBeInTheDocument();
  });

  it("warns when native AR does not represent complete historical evidence", () => {
    vi.mocked(invoiceHooks.useCustomerBalance).mockReturnValue(query({ currency: "USD", open_balance: "75.00", native_invoice_count: 1, applied_payment_total: "25.00", unapplied_receipt_total: "0.00", legacy_evidence_incomplete: true, as_of: "2026-09-12", evidence_classifications: [{ company_id: "company-1", customer_id: "customer-1", source_system: "acp_native", source_record_identity: "customer-1", as_of: "2026-09-12", acquired_at: null, evidence_digest: "a", completeness: "partial", conflict_state: "none", classification: "PARTIAL", authority: "native_invoice_and_receipt_authority" }] }) as never);
    render(<MemoryRouter><CustomerOperationsPanel customerId="customer-1" locations={[]} /></MemoryRouter>);
    expect(screen.getByText("Evidence is partial")).toBeInTheDocument();
  });

  it("does not confuse an unapplied receipt with an Invoice payment", () => {
    render(<MemoryRouter><CustomerOperationsPanel customerId="customer-1" locations={[]} /></MemoryRouter>);
    expect(screen.getByText("Unapplied receipts")).toBeInTheDocument();
    expect(screen.getByText(/Unapplied receipts remain separate Customer credit evidence/)).toBeInTheDocument();
  });

  it("labels a failed Customer balance read unavailable without showing zero", () => {
    vi.mocked(invoiceHooks.useCustomerBalance).mockReturnValue({ data: undefined, isLoading: false, isError: true, isSuccess: false } as never);
    render(<MemoryRouter><CustomerOperationsPanel customerId="customer-1" locations={[]} /></MemoryRouter>);
    expect(screen.getByText("Balance evidence unavailable")).toBeInTheDocument();
    expect(screen.getByText(/No zero balance is inferred/)).toBeInTheDocument();
  });

  it.each([["HISTORICAL_SOURCE_EVIDENCE", "Historical source evidence"], ["STALE", "Source evidence is stale"], ["CONFLICTING", "Evidence conflicts"], ["PARTIAL", "Evidence is partial"], ["UNAVAILABLE", "Evidence unavailable"]])("renders source classification %s without exposing evidence IDs", (classification, label) => {
    vi.mocked(invoiceHooks.useCustomerBalance).mockReturnValue(query({ currency: "USD", open_balance: "75.00", native_invoice_count: 1, applied_payment_total: "25.00", unapplied_receipt_total: "0.00", legacy_evidence_incomplete: false, as_of: "2026-09-12", evidence_classifications: [{ company_id: "company-1", customer_id: "customer-1", source_system: "acp_native", classification: "CURRENT_AUTHORITATIVE", completeness: "complete", conflict_state: "none", source_record_identity: "customer-1", as_of: "2026-09-12", acquired_at: null, evidence_digest: "native-secret-id", authority: "native_invoice_and_receipt_authority" }, { company_id: "company-1", customer_id: "customer-1", source_system: "housecall_pro", classification, completeness: classification === "PARTIAL" ? "partial" : "complete", conflict_state: classification === "CONFLICTING" ? "conflicting" : "none", source_record_identity: "protected-source-id", as_of: "2026-08-31", acquired_at: "2026-09-01T00:00:00Z", evidence_digest: "protected-digest", authority: "historical_source_evidence_only" }] }) as never);
    render(<MemoryRouter><CustomerOperationsPanel customerId="customer-1" locations={[]} /></MemoryRouter>);
    expect(screen.getByText(label)).toBeInTheDocument();
    expect(screen.queryByText("protected-source-id")).not.toBeInTheDocument();
    expect(screen.queryByText("protected-digest")).not.toBeInTheDocument();
  });
});
