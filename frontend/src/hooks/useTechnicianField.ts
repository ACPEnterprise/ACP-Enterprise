import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import * as api from "../api/technicianField";
import type { CustomerDisposition, FieldNoteType } from "../types/technicianField";

const key = (jobId: string) => ["technician-field", jobId] as const;

export function useFieldJobState(jobId: string, enabled = true) {
  return useQuery({
    queryKey: key(jobId),
    queryFn: () => api.getFieldJob(jobId),
    enabled: Boolean(jobId) && enabled,
  });
}

export function useTechnicianField(jobId: string, jobVersion: number, assignmentVersion: number) {
  const client = useQueryClient();
  const update = (value: Awaited<ReturnType<typeof api.getFieldJob>>) => client.setQueryData(key(jobId), value);
  return {
    state: useFieldJobState(jobId),
    note: useMutation({ mutationFn: (input: { noteType: FieldNoteType; content: string }) => api.addWorkNote(jobId, input.noteType, input.content, jobVersion, assignmentVersion), onSuccess: update }),
    approval: useMutation({
      mutationFn: (input: { disposition: CustomerDisposition; customerName: string; reason: string }) =>
        api.recordCustomerDisposition(jobId, input.disposition, input.customerName, input.reason, jobVersion, assignmentVersion),
      onSuccess: update,
    }),
    handoff: useMutation({ mutationFn: () => api.refreshInvoiceHandoff(jobId, jobVersion, assignmentVersion), onSuccess: update }),
    arrival: useMutation({ mutationFn: (input: { appointmentId: string; state: "en_route" | "arrived"; version: number }) => api.recordArrival(input.appointmentId, input.state, input.version), onSuccess: () => client.invalidateQueries({ queryKey: ["technician-itinerary"] }) }),
    lifecycle: useMutation({ mutationFn: (input: { action: "start" | "pause" | "resume" | "complete"; version: number }) => api.transitionJob(jobId, input.action, input.version), onSuccess: () => { void client.invalidateQueries({ queryKey: ["technician-itinerary"] }); void client.invalidateQueries({ queryKey: key(jobId) }); } }),
  };
}
