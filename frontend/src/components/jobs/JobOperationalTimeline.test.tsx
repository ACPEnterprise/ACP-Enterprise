import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { useHasPermission } from "../../auth";
import { useInvoices } from "../../hooks/useInvoices";
import type { JobDetail } from "../../types/jobs";
import { JobOperationalTimeline } from "./JobOperationalTimeline";

vi.mock("../../auth"); vi.mock("../../hooks/useInvoices");
const job = { id: "job-1", job_number: "J-1", created_at: "2026-01-01T10:00:00Z", activated_at: "2026-01-01T11:00:00Z", started_at: "2026-01-02T10:00:00Z", completed_at: "2026-01-02T12:00:00Z", appointments: [{ appointment_id: "apt-1", appointment_number: "A-1", arrival_window_start_at: "2026-01-02T09:00:00Z" }] } as unknown as JobDetail;
describe("JobOperationalTimeline", () => {
  it("orders explicit cross-domain timestamps and links by authoritative identity", () => {
    vi.mocked(useHasPermission).mockReturnValue(true); vi.mocked(useInvoices).mockReturnValue({ data: [{ id: "inv-1", job_id: "job-1", invoice_number: "I-1", created_at: "2026-01-02T13:00:00Z", issued_at: null, status: "draft" }] } as never);
    render(<MemoryRouter><JobOperationalTimeline job={job} /></MemoryRouter>);
    expect(screen.getByText("Appointment scheduled")).toBeVisible();
    expect(screen.getByText("Invoice handoff created")).toBeVisible();
    expect(screen.getAllByRole("link", { name: "Open" }).map((link) => link.getAttribute("href"))).toEqual(["/appointments/apt-1", "/invoices/inv-1"]);
    expect(screen.getByText(/Missing evidence remains absent/)).toBeVisible();
  });
});
