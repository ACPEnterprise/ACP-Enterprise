import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as auth from "../../auth";
import * as estimateHooks from "../../hooks/useEstimates";
import * as invoiceHooks from "../../hooks/useInvoices";
import * as jobHooks from "../../hooks/useJobs";
import * as schedulingHooks from "../../hooks/useScheduling";
import { CustomerOperationsPanel } from "./CustomerOperationsPanel";

vi.mock("../../auth");
vi.mock("../../hooks/useEstimates");
vi.mock("../../hooks/useInvoices");
vi.mock("../../hooks/useJobs");
vi.mock("../../hooks/useScheduling");

const query = (data: unknown) => ({ data, isLoading: false, isError: false, isSuccess: true });
const job = (id: string, status: string, appointmentCount = 0) => ({ id, job_number: id.toUpperCase(), status, appointment_count: appointmentCount, service_location_label: "10 Main Street", updated_at: "2026-09-12T00:00:00Z" });

describe("CustomerOperationsPanel office workflow", () => {
  beforeEach(() => {
    vi.mocked(auth.useHasPermission).mockReturnValue(true);
    vi.mocked(jobHooks.useJobs).mockImplementation((filters) => query(filters.status?.includes("completed")
      ? { items: [job("job-history", "completed", 1)], total_count: 1 }
      : { items: [job("job-current", "ready")], total_count: 1 }) as never);
    vi.mocked(schedulingHooks.useAppointments).mockReturnValue(query({ items: [{ id: "appointment-1", appointment_number: "APT-1", arrival_window_start_at: "2026-09-12T14:00:00Z", status: "scheduled" }] }) as never);
    vi.mocked(estimateHooks.useEstimates).mockReturnValue(query({ items: [{ id: "estimate-1", estimate_number: "EST-1", proposal_title: "Repair", status: "approved" }] }) as never);
    vi.mocked(invoiceHooks.useInvoiceWorkspace).mockReturnValue(query([{ id: "invoice-1", invoice_number: "INV-1", currency: "USD", open_amount: "75.00", status: "partially_paid" }, { id: "invoice-paid", invoice_number: "INV-PAID", currency: "USD", open_amount: "0.00", status: "paid" }]) as never);
    vi.mocked(invoiceHooks.useCustomerBalance).mockReturnValue(query({ currency: "USD", open_balance: "75.00", native_invoice_count: 2, applied_payment_total: "25.00", unapplied_receipt_total: "10.00", legacy_evidence_incomplete: false, as_of: "2026-09-12", evidence_classifications: [{ company_id: "company-1", customer_id: "customer-1", source_system: "acp_native", source_record_identity: "customer-1", as_of: "2026-09-12", acquired_at: "2026-09-12T00:00:00Z", evidence_digest: "a", completeness: "complete", conflict_state: "none", classification: "CURRENT_AUTHORITATIVE", authority: "native_invoice_and_receipt_authority" }] }) as never);
  });

  it("separates current and historical work and preserves action context", () => {
    render(<MemoryRouter><CustomerOperationsPanel customerId="customer-1" /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Current Jobs" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Historical Jobs" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Create Job" })).toHaveAttribute("href", "/jobs?create=1&customerId=customer-1");
    expect(screen.getByRole("link", { name: "Open Job to schedule" })).toHaveAttribute("href", "/jobs/job-current");
    expect(screen.getByRole("link", { name: /APT-1/ })).toHaveAttribute("href", "/appointments/appointment-1");
    expect(screen.getByRole("link", { name: /INV-1/ })).toHaveAttribute("href", "/invoices/invoice-1");
    expect(screen.getByRole("link", { name: /INV-PAID/ })).toHaveAttribute("href", "/invoices/invoice-paid");
    expect(screen.getByRole("link", { name: "Open Invoice / AR workspace" })).toHaveAttribute("href", "/invoices?customerId=customer-1");
    expect(screen.getAllByText("USD 75.00").length).toBeGreaterThan(0);
  });

  it("does not turn absent related evidence into fabricated relationships or zero", () => {
    vi.mocked(jobHooks.useJobs).mockReturnValue(query({ items: [], total_count: 0 }) as never);
    vi.mocked(schedulingHooks.useAppointments).mockReturnValue(query({ items: [] }) as never);
    vi.mocked(estimateHooks.useEstimates).mockReturnValue(query({ items: [] }) as never);
    vi.mocked(invoiceHooks.useInvoiceWorkspace).mockReturnValue(query([]) as never);
    vi.mocked(invoiceHooks.useCustomerBalance).mockReturnValue({ data: undefined, isLoading: false, isError: false, isSuccess: true } as never);
    render(<MemoryRouter><CustomerOperationsPanel customerId="customer-1" /></MemoryRouter>);
    expect(screen.getByText("No current Jobs are linked in native Job authority.")).toBeInTheDocument();
    expect(screen.getByText("No historical Jobs are present in native Job authority.")).toBeInTheDocument();
    expect(screen.getByText(/Balance evidence unavailable/)).toBeInTheDocument();
  });

  it("marks the workspace partial when an owning domain is unavailable", () => {
    vi.mocked(estimateHooks.useEstimates).mockReturnValue({ data: undefined, isLoading: false, isError: true, isSuccess: false } as never);
    render(<MemoryRouter><CustomerOperationsPanel customerId="customer-1" /></MemoryRouter>);
    expect(screen.getByText("Related work is partial")).toBeInTheDocument();
    expect(screen.getByText(/do not treat missing sections or amounts as complete/i)).toBeInTheDocument();
  });

  it("warns when native AR does not represent complete historical evidence", () => {
    vi.mocked(invoiceHooks.useCustomerBalance).mockReturnValue(query({ currency: "USD", open_balance: "75.00", native_invoice_count: 1, applied_payment_total: "25.00", unapplied_receipt_total: "0.00", legacy_evidence_incomplete: true, as_of: "2026-09-12", evidence_classifications: [{ company_id: "company-1", customer_id: "customer-1", source_system: "acp_native", source_record_identity: "customer-1", as_of: "2026-09-12", acquired_at: null, evidence_digest: "a", completeness: "partial", conflict_state: "none", classification: "PARTIAL", authority: "native_invoice_and_receipt_authority" }] }) as never);
    render(<MemoryRouter><CustomerOperationsPanel customerId="customer-1" /></MemoryRouter>);
    expect(screen.getByText("Evidence is partial")).toBeInTheDocument();
  });

  it("does not confuse an unapplied receipt with an Invoice payment", () => {
    render(<MemoryRouter><CustomerOperationsPanel customerId="customer-1" /></MemoryRouter>);
    expect(screen.getByText("Unapplied receipts")).toBeInTheDocument();
    expect(screen.getByText(/Unapplied receipts remain separate Customer credit evidence/)).toBeInTheDocument();
  });

  it("labels a failed Customer balance read unavailable without showing zero", () => {
    vi.mocked(invoiceHooks.useCustomerBalance).mockReturnValue({ data: undefined, isLoading: false, isError: true, isSuccess: false } as never);
    render(<MemoryRouter><CustomerOperationsPanel customerId="customer-1" /></MemoryRouter>);
    expect(screen.getByText("Balance evidence unavailable")).toBeInTheDocument();
    expect(screen.getByText(/No zero balance is inferred/)).toBeInTheDocument();
  });

  it.each([["HISTORICAL_SOURCE_EVIDENCE", "Historical source evidence"], ["STALE", "Source evidence is stale"], ["CONFLICTING", "Evidence conflicts"], ["PARTIAL", "Evidence is partial"], ["UNAVAILABLE", "Evidence unavailable"]])("renders source classification %s without exposing evidence IDs", (classification, label) => {
    vi.mocked(invoiceHooks.useCustomerBalance).mockReturnValue(query({ currency: "USD", open_balance: "75.00", native_invoice_count: 1, applied_payment_total: "25.00", unapplied_receipt_total: "0.00", legacy_evidence_incomplete: false, as_of: "2026-09-12", evidence_classifications: [{ company_id: "company-1", customer_id: "customer-1", source_system: "acp_native", classification: "CURRENT_AUTHORITATIVE", completeness: "complete", conflict_state: "none", source_record_identity: "customer-1", as_of: "2026-09-12", acquired_at: null, evidence_digest: "native-secret-id", authority: "native_invoice_and_receipt_authority" }, { company_id: "company-1", customer_id: "customer-1", source_system: "housecall_pro", classification, completeness: classification === "PARTIAL" ? "partial" : "complete", conflict_state: classification === "CONFLICTING" ? "conflicting" : "none", source_record_identity: "protected-source-id", as_of: "2026-08-31", acquired_at: "2026-09-01T00:00:00Z", evidence_digest: "protected-digest", authority: "historical_source_evidence_only" }] }) as never);
    render(<MemoryRouter><CustomerOperationsPanel customerId="customer-1" /></MemoryRouter>);
    expect(screen.getByText(label)).toBeInTheDocument();
    expect(screen.queryByText("protected-source-id")).not.toBeInTheDocument();
    expect(screen.queryByText("protected-digest")).not.toBeInTheDocument();
  });
});
