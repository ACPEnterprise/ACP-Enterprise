import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MaterialCostReadinessCard } from "./MaterialCostReadinessCard";

describe("MaterialCostReadinessCard", () => {
  it("keeps receipt evidence separate from valuation policy", () => {
    render(<MaterialCostReadinessCard
      items={[{ id: "item-1", name: "Filter" } as never]}
      data={{
        evidence: [{
          inventory_item_id: "item-1", vendor_id: "vendor-1", vendor_name: "Supply Co",
          purchase_order_id: "po-1", purchase_order_line_id: "line-1", receipt_id: "receipt-1",
          receipt_line_id: "receipt-line-1", received_at: "2026-09-15T12:00:00Z",
          effective_date: "2026-09-15", accepted_quantity: "4", unit: "each",
          unit_cost: "12.50", currency: "USD", source_reference: "packing-slip-1",
          authority_state: "ACTUAL_RECEIPT",
        }],
        readiness: [{
          inventory_item_id: "item-1", on_hand_quantity: "4",
          actual_receipt_cost_available: true, currencies: ["USD"],
          readiness_state: "POLICY_OR_SOURCE_REQUIRED",
          blockers: ["VALUATION_METHOD_POLICY_REQUIRED"],
        }],
      }}
    />);
    expect(screen.getByText(/valuation-method policy is still required/i)).toBeInTheDocument();
    expect(screen.getByText(/4 each at 12.50 USD/i)).toBeInTheDocument();
    expect(screen.getByText(/not an Accounting valuation/i)).toBeInTheDocument();
  });
});
