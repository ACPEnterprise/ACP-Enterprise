import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  useCycleCounts,
  useInventory,
  useInventoryMutations,
} from "../hooks/useInventory";
import { InventoryRoute } from "./InventoryRoute";

let permissions = new Set<string>();
vi.mock("../auth", () => ({
  useAuth: () => ({
    activeCompany: {
      id: "company-1",
      branches: [{ id: "branch-1", name: "Main Branch", code: "MAIN" }],
    },
  }),
  useHasPermission: (code: string) => permissions.has(code),
}));
vi.mock("../hooks/useInventory", () => ({
  useInventory: vi.fn(),
  useCycleCounts: vi.fn(),
  useInventoryMutations: vi.fn(),
}));

const mutateAsync = {
  createLocation: vi.fn(),
  transfer: vi.fn(),
  createReservation: vi.fn(),
  allocate: vi.fn(),
  release: vi.fn(),
  adjust: vi.fn(),
  startCount: vi.fn(),
  recordCount: vi.fn(),
  completeCount: vi.fn(),
};

const mutation = (fn: ReturnType<typeof vi.fn>) => ({
  mutateAsync: fn,
  isPending: false,
  isError: false,
});

describe("InventoryRoute", () => {
  beforeEach(() => {
    permissions = new Set(["COMPANY_INVENTORY_READ"]);
    Object.values(mutateAsync).forEach((mock) => mock.mockReset());
    vi.mocked(useInventory).mockReturnValue({
      isPending: false,
      isError: false,
      data: {
        items: [{ id: "item-1", name: "Filter", stocking_unit: "each" }],
        locations: [{ id: "location-1", name: "Main warehouse" }],
        quantities: [],
        reservations: [
          {
            id: "reservation-1",
            item_id: "item-1",
            location_id: "location-1",
            allocated_quantity: "0",
            quantity: "2",
            stocking_unit: "each",
            status: "requested",
            version: 1,
          },
        ],
      },
    } as never);
    vi.mocked(useCycleCounts).mockReturnValue({
      isPending: false,
      isError: false,
      data: [
        {
          id: "count-1",
          branch_id: "branch-1",
          location_id: "location-1",
          name: "August count",
          status: "completed",
          version: 2,
          started_at: "2026-08-29T12:00:00Z",
          completed_at: "2026-08-29T13:00:00Z",
          entries: [],
        },
      ],
    } as never);
    vi.mocked(useInventoryMutations).mockReturnValue({
      createLocation: mutation(mutateAsync.createLocation),
      transfer: mutation(mutateAsync.transfer),
      createReservation: mutation(mutateAsync.createReservation),
      allocate: mutation(mutateAsync.allocate),
      release: mutation(mutateAsync.release),
      adjust: mutation(mutateAsync.adjust),
      startCount: mutation(mutateAsync.startCount),
      recordCount: mutation(mutateAsync.recordCount),
      completeCount: mutation(mutateAsync.completeCount),
    } as never);
  });

  it("keeps count evidence visible but mutation controls permission-gated", () => {
    const { rerender } = render(<InventoryRoute />);
    fireEvent.change(screen.getByLabelText("Inventory Branch"), {
      target: { value: "branch-1" },
    });
    expect(screen.getByText("Physical count history")).toBeVisible();
    expect(screen.getByText("August count")).toBeVisible();
    expect(
      screen.queryByText("Post inventory adjustment"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("Physical count", { selector: "h3" }),
    ).not.toBeInTheDocument();

    permissions.add("COMPANY_INVENTORY_ADJUST");
    permissions.add("COMPANY_INVENTORY_COUNT");
    rerender(<InventoryRoute />);
    expect(screen.getByText("Post inventory adjustment")).toBeVisible();
    expect(
      screen.getByText("Physical count", { selector: "h3" }),
    ).toBeVisible();
  });

  it("keeps mutation controls hidden from read-only users", () => {
    render(<InventoryRoute />);
    expect(screen.getByText("Location balances")).toBeVisible();
    expect(screen.queryByText("Create stock location")).not.toBeInTheDocument();
    expect(screen.queryByText("Create reservation")).not.toBeInTheDocument();
    expect(screen.queryByText("Allocate available")).not.toBeInTheDocument();
  });

  it("creates a Branch-scoped location through the existing command", async () => {
    permissions.add("COMPANY_INVENTORY_MANAGE");
    render(<InventoryRoute />);
    fireEvent.change(screen.getByLabelText("Inventory Branch"), {
      target: { value: "branch-1" },
    });
    fireEvent.change(screen.getByLabelText("Location code"), {
      target: { value: "VAN-1" },
    });
    fireEvent.change(screen.getByLabelText("Location name"), {
      target: { value: "Service van 1" },
    });
    fireEvent.change(screen.getByLabelText("Location type"), {
      target: { value: "vehicle" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create location" }));
    await waitFor(() =>
      expect(mutateAsync.createLocation).toHaveBeenCalledWith({
        branch_id: "branch-1",
        code: "VAN-1",
        name: "Service van 1",
        location_type: "vehicle",
      }),
    );
  });

  it("creates and allocates reservations without changing on-hand", async () => {
    permissions.add("COMPANY_INVENTORY_RESERVE");
    render(<InventoryRoute />);
    fireEvent.change(screen.getByLabelText("Inventory Branch"), {
      target: { value: "branch-1" },
    });
    fireEvent.change(screen.getByLabelText("Reservation item"), {
      target: { value: "item-1" },
    });
    fireEvent.change(screen.getByLabelText("Reservation location"), {
      target: { value: "location-1" },
    });
    fireEvent.change(screen.getByLabelText("Reservation quantity"), {
      target: { value: "2" },
    });
    fireEvent.change(screen.getByLabelText("Demand ID"), {
      target: { value: "00000000-0000-0000-0000-000000000001" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create reservation" }));
    await waitFor(() =>
      expect(mutateAsync.createReservation).toHaveBeenCalledWith(
        expect.objectContaining({
          branch_id: "branch-1",
          item_id: "item-1",
          location_id: "location-1",
          quantity: "2",
          demand_type: "job",
        }),
      ),
    );

    fireEvent.click(screen.getByRole("button", { name: "Allocate available" }));
    expect(mutateAsync.allocate).toHaveBeenCalledWith({
      id: "reservation-1",
      data: expect.objectContaining({
        expected_version: 1,
        allow_partial: true,
        quantity: null,
      }),
    });
  });
});
