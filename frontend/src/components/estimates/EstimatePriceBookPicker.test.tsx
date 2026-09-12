import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EstimatePriceBookPicker } from "./EstimatePriceBookPicker";

vi.mock("../../hooks/usePriceBook", () => ({ useEffectivePriceBook: () => ({ data: { items: [{ item_id: "item-1", item_code: "DRAIN", item_name: "Drain service", customer_description: "Clear customer drain", category_id: "category-1", category_name: "Drain", price_version_id: "version-1", unit_price: "125.00", currency: "USD", effective_at: "2026-09-01T00:00:00Z", expires_at: null, tax_classification_name: "Service", taxable: false, options: [{ group_id: "group-1", group_name: "Service level", minimum_selections: 1, maximum_selections: 1, option_id: "option-1", option_label: "Standard" }] }] } }) }));

describe("EstimatePriceBookPicker", () => {
  it("shows operator-safe effective details and validates required options", () => {
    const add = vi.fn().mockResolvedValue(undefined);
    render(<EstimatePriceBookPicker branchId="branch-1" effectiveAt="2026-09-12T12:00:00Z" pending={false} onAdd={add} />);
    expect(screen.getByText("Drain service")).toBeVisible();
    expect(screen.getByText("$125.00")).toBeVisible();
    expect(screen.queryByText("version-1")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Select service" }));
    expect(screen.getByRole("button", { name: "Add to Estimate" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Service option"), { target: { value: "group-1:option-1" } });
    fireEvent.change(screen.getByLabelText("Service quantity"), { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: "Add to Estimate" }));
    expect(add).toHaveBeenCalledWith(expect.objectContaining({ item_id: "item-1" }), "2", { groupId: "group-1", optionId: "option-1" });
  });
});
