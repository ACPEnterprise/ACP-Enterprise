import { useQuery } from "@tanstack/react-query";
import {
  getCashOperationalEconomics,
  getEconomicsPolicyAdministration,
  getEconomicsResult,
  getEconomicsResultLineage,
  getEconomicsWorkspace,
  getOwnerIntelligence,
  getOperationalSourceEconomics,
  type OwnerQuestion,
} from "../api/businessEconomics";

export function useEconomicsWorkspace(
  start: string,
  end: string,
  enabled = true,
) {
  return useQuery({
    queryKey: ["business-economics", "workspace", start, end],
    queryFn: () => getEconomicsWorkspace(start, end),
    enabled,
  });
}
export function useOperationalSourceEconomics(start: string, end: string, enabled = true) {
  return useQuery({
    queryKey: ["business-economics", "operational-sources", start, end],
    queryFn: () => getOperationalSourceEconomics(start, end),
    enabled,
  });
}
export function useEconomicsResult(resultId: string | null, enabled = true) {
  return useQuery({
    queryKey: ["business-economics", "result", resultId],
    queryFn: () => getEconomicsResult(resultId!),
    enabled: enabled && Boolean(resultId),
  });
}
export function useOwnerIntelligence(
  question: OwnerQuestion,
  start: string,
  end: string,
  enabled = true,
) {
  return useQuery({
    queryKey: [
      "business-economics",
      "owner-intelligence",
      question,
      start,
      end,
    ],
    queryFn: () => getOwnerIntelligence(question, start, end),
    enabled,
  });
}
export function useCashOperationalEconomics(
  start: string,
  end: string,
  enabled = true,
) {
  return useQuery({
    queryKey: ["business-economics", "cash-operational", start, end],
    queryFn: () => getCashOperationalEconomics(start, end),
    enabled,
  });
}
export function useEconomicsPolicyAdministration(
  start: string,
  end: string,
  enabled = true,
) {
  return useQuery({
    queryKey: ["business-economics", "policy-administration", start, end],
    queryFn: () => getEconomicsPolicyAdministration(start, end),
    enabled,
  });
}
export function useEconomicsResultLineage(
  resultId: string | null,
  enabled = true,
) {
  return useQuery({
    queryKey: ["business-economics", "result-lineage", resultId],
    queryFn: () => getEconomicsResultLineage(resultId!),
    enabled: enabled && Boolean(resultId),
  });
}
