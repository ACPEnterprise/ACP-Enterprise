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

export async function getRevenueTrend(): Promise<RevenueTrend> {
  const response = await apiClient.get<RevenueTrend>(
    "/api/v1/analytics/revenue-trend",
  );

  return response.data;
}
