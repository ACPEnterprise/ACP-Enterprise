import { useMutation, useQueryClient } from "@tanstack/react-query";

import { assignPrimary } from "../api/dispatch";
import { createServiceRequest, scheduleExistingJob } from "../api/operations";
import type { ExistingJobScheduleInput, ServiceRequestCreateInput } from "../types/operations";
import { jobKeys } from "./useJobs";
import { appointmentKeys } from "./useScheduling";

export function useCreateServiceRequest() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: ServiceRequestCreateInput) => createServiceRequest(input),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: appointmentKeys.lists() }),
        client.invalidateQueries({ queryKey: jobKeys.lists() }),
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
        await assignPrimary(
          result.appointment.id,
          employeeId,
          "Office assignment while scheduling Job",
        );
      }
      return result;
    },
    onSuccess: async () => {
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
