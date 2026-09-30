import type { DispatchPlacementRecommendation, GhostSlotClass } from "../../types/dispatch";

export function ghostSlotClass(candidate: DispatchPlacementRecommendation): GhostSlotClass {
  if (candidate.eligible && candidate.rank === 1) return "PRIMARY_GHOST_SLOT";
  if (candidate.eligible) return "ALTERNATE_GHOST_SLOT";
  if (candidate.constraints.some((item) => item.result === "FAIL")) return "CONSTRAINED_OPTION";
  return "UNAVAILABLE";
}
