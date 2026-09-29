import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { shouldRetryApiQuery } from "../api/errors";
import {
  getAppointment,
  getBranchSchedulingPolicy,
  getBranchCalendarRoster,
  configureBranchSchedulingPolicy,
  listAppointments,
  rescheduleAppointment,
} from "../api/scheduling";
import type {
  AppointmentListParams,
  AppointmentRescheduleInput,
  BranchSchedulingPolicyInput,
} from "../types/scheduling";

export const appointmentKeys = {
  all: ["appointments"] as const,
  detail: (id: string) => ["appointments", "detail", id] as const,
  lists: () => ["appointments", "list"] as const,
  list: (query: AppointmentListParams) =>
    ["appointments", "list", query] as const,
};

export function useBranchSchedulingPolicy(branchId: string | undefined) {
  return useQuery({
    queryKey: ["scheduling", "branch-policy", branchId],
    queryFn: () => getBranchSchedulingPolicy(branchId as string),
    enabled: Boolean(branchId),
    retry: shouldRetryApiQuery,
  });
}

export function useBranchCalendarRoster(
  branchId: string | undefined,
  startAt: string,
  endAt: string,
) {
  return useQuery({
    queryKey: ["scheduling", "branch-calendar-roster", branchId, startAt, endAt],
    queryFn: () => getBranchCalendarRoster(branchId as string, startAt, endAt),
    enabled: Boolean(branchId),
    retry: shouldRetryApiQuery,
  });
}

export function useConfigureBranchSchedulingPolicy() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ branchId, input }: { branchId: string; input: BranchSchedulingPolicyInput }) =>
      configureBranchSchedulingPolicy(branchId, input),
    onSuccess: async (_, variables) => {
      await client.invalidateQueries({ queryKey: ["scheduling", "branch-policy", variables.branchId] });
    },
  });
}

export function useAppointment(
  appointmentId: string | undefined,
  enabled = true,
) {
  return useQuery({
    queryKey: appointmentKeys.detail(appointmentId ?? ""),
    queryFn: () => getAppointment(appointmentId as string),
    enabled: enabled && Boolean(appointmentId),
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

export function useRescheduleAppointment() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      appointmentId,
      input,
    }: {
      appointmentId: string;
      input: AppointmentRescheduleInput;
    }) => rescheduleAppointment(appointmentId, input),
    onSettled: async (_, __, variables) => {
      await Promise.all([
        client.invalidateQueries({ queryKey: appointmentKeys.lists() }),
        client.invalidateQueries({
          queryKey: appointmentKeys.detail(variables.appointmentId),
        }),
        client.invalidateQueries({ queryKey: ["dispatch"] }),
      ]);
    },
  });
}
