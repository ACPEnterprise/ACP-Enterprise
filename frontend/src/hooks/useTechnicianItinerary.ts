import { useQuery } from "@tanstack/react-query";

import { getTechnicianItinerary } from "../api/technician";

export const technicianKeys = {
  all: ["technician"] as const,
  itinerary: (serviceDate: string) =>
    ["technician", "itinerary", serviceDate] as const,
};

export function useTechnicianItinerary(serviceDate: string) {
  return useQuery({
    queryKey: technicianKeys.itinerary(serviceDate),
    queryFn: () => getTechnicianItinerary(serviceDate),
  });
}
