import type { AnalyticsSummary } from "../types/analytics";
import { apiClient } from "./client";

export async function getAnalyticsSummary(): Promise<AnalyticsSummary> {
  const response = await apiClient.get<AnalyticsSummary>(
    "/api/v1/analytics/summary",
  );

  return response.data;
}
