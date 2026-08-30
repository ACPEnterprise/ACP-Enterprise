import { useQuery } from "@tanstack/react-query";
import { getEconomicsResult, getEconomicsWorkspace, getOwnerIntelligence, type OwnerQuestion } from "../api/businessEconomics";

export function useEconomicsWorkspace(start: string, end: string, enabled = true) { return useQuery({ queryKey: ["business-economics", "workspace", start, end], queryFn: () => getEconomicsWorkspace(start, end), enabled }); }
export function useEconomicsResult(resultId: string | null, enabled = true) { return useQuery({ queryKey: ["business-economics", "result", resultId], queryFn: () => getEconomicsResult(resultId!), enabled: enabled && Boolean(resultId) }); }
export function useOwnerIntelligence(question: OwnerQuestion, start: string, end: string, enabled = true) { return useQuery({ queryKey: ["business-economics", "owner-intelligence", question, start, end], queryFn: () => getOwnerIntelligence(question, start, end), enabled }); }
