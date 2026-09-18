import { useQuery } from "@tanstack/react-query";

import { shouldRetryApiQuery } from "../api/errors";
import { getFactoryControlOverview, getFactoryLaneDrilldown, type FactoryControlFilters } from "../api/factoryControl";

export function useFactoryControlOverview(filters: FactoryControlFilters, enabled: boolean) {
  return useQuery({
    queryKey: ["factory-control", "overview", filters.lane ?? "all"],
    queryFn: getFactoryControlOverview,
    enabled,
    retry: shouldRetryApiQuery,
    staleTime: 15_000,
  });
}

export function useFactoryLaneDrilldown(lane: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["factory-control", "lane", lane],
    queryFn: () => getFactoryLaneDrilldown(lane!),
    enabled: enabled && Boolean(lane),
    retry: shouldRetryApiQuery,
    staleTime: 15_000,
  });
}
