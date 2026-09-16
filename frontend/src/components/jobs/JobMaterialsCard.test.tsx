import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { JobMaterials } from "../../types/inventory";
import { JobMaterialsCard } from "./JobMaterialsCard";

describe("JobMaterialsCard", () => {
  it("keeps expected, reserved, and consumed material truth distinct", () => {
    const materials: JobMaterials = {
      job_id: "job-1",
      branch_id: "branch-1",
      readiness_state: "NEEDS_ATTENTION",
      blockers: ["RESERVATION_REQUIRED"],
      requirements: [{
        component_code: "PIPE-1", label: "Pipe", requirement_type: "required",
        expected_quantity: "6", inventory_item_id: "item-1", stocking_unit: "each",
        on_hand_quantity: "10", available_quantity: "8", reserved_quantity: "2",
        consumed_quantity: "1", readiness_state: "READY_TO_RESERVE", blockers: ["RESERVATION_REQUIRED"],
        source_snapshot_ids: ["snapshot-1"], source_snapshot_digests: ["digest-1"],
      }],
    };

    render(<JobMaterialsCard materials={materials} />);

    expect(screen.getByText("Job materials")).toBeInTheDocument();
    expect(screen.getByText("reservation required")).toBeInTheDocument();
    expect(screen.getByText("6 each")).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
  });

  it("shows unknown quantities instead of false zero for an unbound part", () => {
    const materials = {
      job_id: "job-1", branch_id: "branch-1", readiness_state: "NEEDS_ATTENTION",
      blockers: ["INVENTORY_ITEM_BINDING_REQUIRED"], requirements: [{
        component_code: null, label: "Valve", requirement_type: "required", expected_quantity: "1",
        inventory_item_id: null, stocking_unit: null, on_hand_quantity: null,
        available_quantity: null, reserved_quantity: null, consumed_quantity: null,
        readiness_state: "SOURCE_REQUIRED", blockers: ["INVENTORY_ITEM_BINDING_REQUIRED"],
        source_snapshot_ids: ["snapshot-1"], source_snapshot_digests: ["digest-1"],
      }],
    } satisfies JobMaterials;

    render(<JobMaterialsCard materials={materials} />);
    expect(screen.getAllByText("Unknown")).toHaveLength(3);
  });
});
