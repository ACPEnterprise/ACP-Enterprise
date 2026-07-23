import { useQuery } from "@tanstack/react-query";

import { shouldRetryApiQuery } from "../api/errors";
import { getAppointment } from "../api/scheduling";

export const appointmentKeys = {
  all: ["appointments"] as const,
  detail: (id: string) => ["appointments", "detail", id] as const,
};

export function useAppointment(appointmentId: string | undefined) {
  return useQuery({
    queryKey: appointmentKeys.detail(appointmentId ?? ""),
    queryFn: () => getAppointment(appointmentId as string),
    enabled: Boolean(appointmentId),
    retry: shouldRetryApiQuery,
  });
}
