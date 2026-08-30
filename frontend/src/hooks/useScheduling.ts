import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { shouldRetryApiQuery } from "../api/errors";
import { cancelAppointment, createAppointment, getAppointment, listAppointments, rescheduleAppointment } from "../api/scheduling";
import type { AppointmentDetail, AppointmentListParams } from "../types/scheduling";

export const appointmentKeys = {
  all: ["appointments"] as const,
  detail: (id: string) => ["appointments", "detail", id] as const,
  lists: () => ["appointments", "list"] as const,
  list: (query: AppointmentListParams) => ["appointments", "list", query] as const,
};

export function useAppointment(appointmentId: string | undefined) {
  return useQuery({
    queryKey: appointmentKeys.detail(appointmentId ?? ""),
    queryFn: () => getAppointment(appointmentId as string),
    enabled: Boolean(appointmentId),
    retry: shouldRetryApiQuery,
  });
}

export function useAppointments(query: AppointmentListParams, enabled = true) {
  return useQuery({
    queryKey: appointmentKeys.list(query),
    queryFn: () => listAppointments(query),
    enabled,
    retry: shouldRetryApiQuery,
  });
}

export function useSchedulingMutations() {
  const client = useQueryClient();
  const update = (appointment: AppointmentDetail) => {
    client.setQueryData(appointmentKeys.detail(appointment.id), appointment);
    void client.invalidateQueries({ queryKey: appointmentKeys.lists() });
  };
  return {
    create: useMutation({ mutationFn: createAppointment, onSuccess: update }),
    reschedule: useMutation({ mutationFn: ({ id, input }: { id: string; input: Parameters<typeof rescheduleAppointment>[1] }) => rescheduleAppointment(id, input), onSuccess: update }),
    cancel: useMutation({ mutationFn: ({ id, input }: { id: string; input: Parameters<typeof cancelAppointment>[1] }) => cancelAppointment(id, input), onSuccess: update }),
  };
}
