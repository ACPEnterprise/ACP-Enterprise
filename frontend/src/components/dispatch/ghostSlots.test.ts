import { describe, expect, it } from "vitest";
import type { DispatchPlacementRecommendation } from "../../types/dispatch";
import { ghostSlotClass } from "./ghostSlots";

const candidate = (eligible: boolean, rank: number | null, result: "PASS" | "FAIL" | "UNKNOWN"): DispatchPlacementRecommendation => ({
  employee_id: "employee-1",
  proposed_window: { start_at: "2026-09-30T13:00:00Z", end_at: "2026-09-30T14:00:00Z" },
  placement_class: "candidate",
  eligible,
  rank,
  constraints: [{ constraint: "capacity", result, explanation: "Capacity evidence" }],
  tradeoffs: [],
  limitations: [],
  confidence: "COMPLETE",
});

describe("ghostSlotClass", () => {
  it("preserves the qualified non-mutating recommendation classifications", () => {
    expect(ghostSlotClass(candidate(true, 1, "PASS"))).toBe("PRIMARY_GHOST_SLOT");
    expect(ghostSlotClass(candidate(true, 2, "PASS"))).toBe("ALTERNATE_GHOST_SLOT");
    expect(ghostSlotClass(candidate(false, null, "FAIL"))).toBe("CONSTRAINED_OPTION");
    expect(ghostSlotClass(candidate(false, null, "UNKNOWN"))).toBe("UNAVAILABLE");
  });
});
