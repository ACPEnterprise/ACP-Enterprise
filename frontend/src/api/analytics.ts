import type {
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
