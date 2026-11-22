import { useQuery } from "@tanstack/react-query";

import { getAnalyticsMetricDetail } from "../api/analytics";
import type { AnalyticsMetricKey } from "../types/analytics";

export function useAnalyticsMetricDetail(
  metric: AnalyticsMetricKey | null,
  periodStart: string | null,
  periodEnd: string | null,
  enabled = true,
) {
  return useQuery({
    queryKey: ["analytics-metric-detail", metric, periodStart, periodEnd],
    queryFn: () => getAnalyticsMetricDetail(metric as AnalyticsMetricKey, periodStart ?? undefined, periodEnd ?? undefined),
    enabled: enabled && metric !== null,
  });
}
