import { useQuery } from "@tanstack/react-query";

import { getAnalyticsSummary } from "../api/analytics";

export function useAnalyticsSummary(enabled = true) {
  return useQuery({
    queryKey: ["analytics-summary"],
    queryFn: getAnalyticsSummary,
    refetchInterval: 15_000,
    enabled,
  });
}
