import { useMutation, useQueryClient } from "@tanstack/react-query";

import { createServiceRequest, scheduleExistingJob } from "../api/operations";
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

export function useScheduleExistingJob(jobId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: ExistingJobScheduleInput) =>
      scheduleExistingJob(jobId, input),
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
