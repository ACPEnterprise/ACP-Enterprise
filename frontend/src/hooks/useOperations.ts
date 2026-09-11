import { useMutation, useQueryClient } from "@tanstack/react-query";

import { createServiceRequest } from "../api/operations";
import type { ServiceRequestCreateInput } from "../types/operations";
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
