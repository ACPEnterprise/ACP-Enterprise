import { useQuery } from "@tanstack/react-query";
import { getEconomicsResult, getEconomicsWorkspace } from "../api/businessEconomics";

export function useEconomicsWorkspace(start: string, end: string, enabled = true) { return useQuery({ queryKey: ["business-economics", "workspace", start, end], queryFn: () => getEconomicsWorkspace(start, end), enabled }); }
export function useEconomicsResult(resultId: string | null, enabled = true) { return useQuery({ queryKey: ["business-economics", "result", resultId], queryFn: () => getEconomicsResult(resultId!), enabled: enabled && Boolean(resultId) }); }
