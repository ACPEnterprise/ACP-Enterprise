import { useQuery } from "@tanstack/react-query";

import { getRevenueTrend } from "../api/analytics";

export function useRevenueTrend() {
  return useQuery({
    queryKey: ["revenue-trend"],
    queryFn: getRevenueTrend,
    refetchInterval: 30000,
  });
}
