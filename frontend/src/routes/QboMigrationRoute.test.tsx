import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { QboMigrationRoute } from "./QboMigrationRoute";

let allowed = true;
const mutateAsync = vi.fn();
vi.mock("../auth", () => ({ useHasPermission: () => allowed }));
vi.mock("../hooks/useQboNativeApplication", () => ({
  useQboApplicationLedger: () => ({ isPending: false, isError: false, data: {
    source_evidence: { available: true, acquired_at: "2026-08-31T21:00:00Z", total_source_records: 3, source_families: [{ source_family: "invoice", total_source: 3 }] },
    families: [{ source_family: "invoice", total_source: 3, applied: 1, bound: 1, quarantined: 1, provider_unavailable: 0, unsupported: 0, rejected: 0, unexplained: 0, safe_majority_applied_percentage: 66.67 }],
    last_execution: { total_dispositions: 3, last_applied_at: "2026-09-29T10:00:00Z" }, qbo_write_performed: false, accounting_posting_performed: false,
  }}),
  useQboReviewQueue: () => ({ isPending: false, isError: false, data: [{ id: "review-1", source_family: "invoice", provider_record_id: "850", reference_number: "INV-850", source_date: "2026-05-01", source_amount: "850.00", source_entity_names: ["Example Customer"], candidate_native_ids: [], conflicting_fields: ["source_version"], exact_conflict: "The same source version has contradictory content.", affected_dependents: ["payment-1"], allowed_actions: ["HOLD_FOR_ACCOUNTANT"], state: "OPEN" }] }),
  useApplyQboSafeMajority: () => ({ mutateAsync, isPending: false, isSuccess: false, isError: false }),
}));

describe("QboMigrationRoute", () => {
  beforeEach(() => { allowed = true; mutateAsync.mockReset(); });

  it("shows truthful counts and requires explicit confirmation before application", () => {
    render(<QboMigrationRoute />);
    expect(screen.getByRole("heading", { name: /QuickBooks migration and reconciliation/i })).toBeVisible();
    expect(screen.getAllByText("66.67%")).toHaveLength(2);
    expect(screen.getByText(/contradictory content/i)).toBeVisible();
    const button = screen.getByRole("button", { name: /Apply safe majority/i });
    expect(button).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(button);
    expect(mutateAsync).toHaveBeenCalledOnce();
  });

  it("fails closed without reconciliation authority", () => {
    allowed = false;
    render(<QboMigrationRoute />);
    expect(screen.getByText(/reconciliation permission is required/i)).toBeVisible();
  });
});
