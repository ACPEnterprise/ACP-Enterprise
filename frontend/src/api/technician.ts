import type { TechnicianItinerary } from "../types/technician";
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
