import { useMutation, useQueryClient } from "@tanstack/react-query";

import { assignPrimary } from "../api/dispatch";
import { createServiceRequest, placeCalendarAppointment, scheduleExistingJob } from "../api/operations";
import type { ExistingJobScheduleInput, ServiceRequestCreateInput } from "../types/operations";
import { jobKeys } from "./useJobs";
import { appointmentKeys } from "./useScheduling";

export function useCreateServiceRequest() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: ServiceRequestCreateInput) => createServiceRequest(input),
    onSettled: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: appointmentKeys.lists() }),
        client.invalidateQueries({ queryKey: jobKeys.lists() }),
        client.invalidateQueries({ queryKey: ["dispatch"] }),
      ]);
    },
  });
}

export function useCalendarPlacement() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ appointmentId, input }: { appointmentId: string; input: Parameters<typeof placeCalendarAppointment>[1] }) =>
      placeCalendarAppointment(appointmentId, input),
    onSettled: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["appointments"] }),
        client.invalidateQueries({ queryKey: ["dispatch"] }),
      ]);
    },
  });
}

export function useScheduleExistingJob(jobId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (input: ExistingJobScheduleInput) => {
      const { employee_id: employeeId, ...schedule } = input;
      const result = await scheduleExistingJob(jobId, schedule);
      if (employeeId) {
        try {
          await assignPrimary(
            result.appointment.id,
            employeeId,
            "Office assignment while scheduling Job",
            undefined,
            `schedule-assignment:${input.request_id}`,
            input.override_reason_code,
          );
        } catch (assignmentError) {
          return { ...result, assignmentState: "FAILED" as const, assignmentError };
        }
      }
      return {
        ...result,
        assignmentState: employeeId ? "ASSIGNED" as const : "NOT_REQUESTED" as const,
      };
    },
    onSettled: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: appointmentKeys.lists() }),
        client.invalidateQueries({ queryKey: jobKeys.lists() }),
        client.invalidateQueries({ queryKey: jobKeys.detail(jobId) }),
        client.invalidateQueries({ queryKey: ["dispatch"] }),
        client.invalidateQueries({ queryKey: ["technician"] }),
      ]);
    },
  });
}
