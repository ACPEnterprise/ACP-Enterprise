import { useQuery } from "@tanstack/react-query";

import { getTechnicianHistory, getTechnicianItinerary } from "../api/technician";

export const technicianKeys = {
  all: ["technician"] as const,
  itinerary: (serviceDate: string) =>
    ["technician", "itinerary", serviceDate] as const,
  history: (startDate: string, endDate: string, query: string) =>
    ["technician", "history", startDate, endDate, query] as const,
};

export function useTechnicianItinerary(serviceDate: string) {
  return useQuery({
    queryKey: technicianKeys.itinerary(serviceDate),
    queryFn: () => getTechnicianItinerary(serviceDate),
  });
}

export function useTechnicianHistory(startDate: string, endDate: string, query: string, enabled = true) {
  return useQuery({
    queryKey: technicianKeys.history(startDate, endDate, query),
    queryFn: () => getTechnicianHistory({ startDate, endDate, query }),
    enabled,
  });
}
