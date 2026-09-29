import type { TechnicianHistory, TechnicianItinerary } from "../types/technician";
import { apiClient } from "./client";

const TECHNICIAN_PATH = "/api/v1/technician";

export async function getTechnicianItinerary(
  serviceDate: string,
): Promise<TechnicianItinerary> {
  const response = await apiClient.get<TechnicianItinerary>(
    `${TECHNICIAN_PATH}/itinerary`,
    { params: { service_date: serviceDate } },
  );
  return response.data;
}

export async function getTechnicianHistory(input: {
  startDate: string;
  endDate: string;
  query?: string;
}): Promise<TechnicianHistory> {
  const response = await apiClient.get<TechnicianHistory>(`${TECHNICIAN_PATH}/history`, {
    params: {
      start_date: input.startDate,
      end_date: input.endDate,
      ...(input.query?.trim() ? { q: input.query.trim() } : {}),
      limit: 50,
    },
  });
  return response.data;
}
