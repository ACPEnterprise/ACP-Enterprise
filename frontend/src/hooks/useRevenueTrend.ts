import { useQuery } from "@tanstack/react-query";

import { getRevenueTrend } from "../api/analytics";

export function useRevenueTrend(days = 7) {
  return useQuery({
    queryKey: ["revenue-trend", days],
    queryFn: () => getRevenueTrend(days),
    refetchInterval: 30000,
  });
}
