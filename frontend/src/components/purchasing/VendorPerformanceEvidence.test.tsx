import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { VendorPerformanceEvidence } from "./VendorPerformanceEvidence";

vi.mock("../../hooks/useProcurementMatching", () => ({
  useVendorPerformance: () => ({
    isPending: false,
    isError: false,
    data: {
      items: [{
        vendor_id: "vendor-1",
        purchase_order_count: 2,
        ordered_quantity: "10",
        accepted_received_quantity: "8",
        returned_quantity: "1",
        net_accepted_quantity: "7",
        fulfillment_ratio: "0.7000",
        return_ratio: "0.1250",
        completed_lead_time_samples: 1,
        average_lead_time_days: "2.00",
        discrepancy_count: 1,
        price_variance_line_count: 0,
      }],
    },
  }),
}));

describe("VendorPerformanceEvidence", () => {
  it("presents attributable operational measures without inventing a score", () => {
    render(<VendorPerformanceEvidence />);
    expect(screen.getByText(/ordered 10 · accepted 8 · returned 1 · net 7/)).toBeVisible();
    expect(screen.getByText(/average lead time 2.00 days/)).toBeVisible();
    expect(screen.queryByText(/^score/i)).not.toBeInTheDocument();
  });
});
