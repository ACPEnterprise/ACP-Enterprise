import type {
  AnalyticsDrilldown,
  AnalyticsMetricKey,
  AnalyticsSummary,
  RevenueTrend,
} from "../types/analytics";
import { apiClient } from "./client";

export async function getAnalyticsSummary(): Promise<AnalyticsSummary> {
  const response = await apiClient.get<AnalyticsSummary>(
    "/api/v1/analytics/summary",
  );

  return response.data;
}

export async function getRevenueTrend(days = 7): Promise<RevenueTrend> {
  const response = await apiClient.get<RevenueTrend>(
    "/api/v1/analytics/revenue-trend",
    { params: { days } },
  );

  return response.data;
}

export async function getAnalyticsMetricDetail(
  metric: AnalyticsMetricKey,
  periodStart?: string,
  periodEnd?: string,
): Promise<AnalyticsDrilldown> {
  const response = await apiClient.get<AnalyticsDrilldown>(
    "/api/v1/analytics/metric-detail",
    {
      params: {
        metric,
        period_start: periodStart,
        period_end: periodEnd,
      },
    },
  );

  return response.data;
}
