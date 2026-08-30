import { useQuery } from "@tanstack/react-query";
import { getEconomicsResult, getEconomicsWorkspace } from "../api/businessEconomics";

export function useEconomicsWorkspace(start: string, end: string) { return useQuery({ queryKey: ["business-economics", "workspace", start, end], queryFn: () => getEconomicsWorkspace(start, end) }); }
export function useEconomicsResult(resultId: string | null) { return useQuery({ queryKey: ["business-economics", "result", resultId], queryFn: () => getEconomicsResult(resultId!), enabled: Boolean(resultId) }); }
