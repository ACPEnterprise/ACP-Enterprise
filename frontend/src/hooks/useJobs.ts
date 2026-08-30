import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as jobsApi from "../api/jobs";
import type { JobCreateFromAppointmentInput, JobCreateInput, JobListParams } from "../types/jobs";
import { shouldRetryApiQuery } from "../api/errors";
import { appointmentKeys } from "./useScheduling";

export const jobKeys = { all: ["jobs"] as const, lists: () => ["jobs", "list"] as const, list: (query: JobListParams) => ["jobs", "list", query] as const, detail: (id: string) => ["jobs", "detail", id] as const };
export function useJobs(query: JobListParams, enabled = true) { return useQuery({ queryKey: jobKeys.list(query), queryFn: () => jobsApi.listJobs(query), retry: shouldRetryApiQuery, enabled }); }
export function useJob(jobId: string | undefined) { return useQuery({ queryKey: jobKeys.detail(jobId ?? ""), queryFn: () => jobsApi.getJob(jobId as string), enabled: Boolean(jobId), retry: shouldRetryApiQuery }); }
function useJobMutation<T>(mutationFn: (input: T) => Promise<{ id: string }>) { const client = useQueryClient(); return useMutation({ mutationFn, onSuccess: async (job) => { await Promise.all([client.invalidateQueries({ queryKey: jobKeys.lists() }), client.invalidateQueries({ queryKey: jobKeys.detail(job.id) })]); } }); }
export function useCreateJob() { return useJobMutation<JobCreateInput>(jobsApi.createJob); }
export function useJobForAppointment(appointmentId: string | undefined) {
  const query = { appointmentId, page: 1, pageSize: 1 };
  return useQuery({
    queryKey: jobKeys.list(query),
    queryFn: () => jobsApi.listJobs(query),
    enabled: Boolean(appointmentId),
    retry: shouldRetryApiQuery,
  });
}
export function useCreateJobFromAppointment(appointmentId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: Omit<JobCreateFromAppointmentInput, "appointment_id">) => jobsApi.createJobFromAppointment({ ...input, appointment_id: appointmentId }),
    onSuccess: async (job) => {
      await Promise.all([
        client.invalidateQueries({ queryKey: appointmentKeys.detail(appointmentId) }),
        client.invalidateQueries({ queryKey: jobKeys.lists() }),
        client.invalidateQueries({ queryKey: jobKeys.detail(job.id) }),
      ]);
    },
    onError: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: appointmentKeys.detail(appointmentId) }),
        client.invalidateQueries({ queryKey: jobKeys.lists() }),
      ]);
    },
  });
}
export function useActivateJob(id: string) { return useJobMutation((input: Parameters<typeof jobsApi.activateJob>[1]) => jobsApi.activateJob(id, input)); }
export function useStartJob(id: string) { return useJobMutation((input: Parameters<typeof jobsApi.startJob>[1]) => jobsApi.startJob(id, input)); }
export function usePauseJob(id: string) { return useJobMutation((input: Parameters<typeof jobsApi.pauseJob>[1]) => jobsApi.pauseJob(id, input)); }
export function useResumeJob(id: string) { return useJobMutation((input: Parameters<typeof jobsApi.resumeJob>[1]) => jobsApi.resumeJob(id, input)); }
export function useCompleteJob(id: string) { return useJobMutation((input: Parameters<typeof jobsApi.completeJob>[1]) => jobsApi.completeJob(id, input)); }
export function useCancelJob(id: string) { return useJobMutation((input: Parameters<typeof jobsApi.cancelJob>[1]) => jobsApi.cancelJob(id, input)); }
export function useReopenJob(id: string) { return useJobMutation((input: Parameters<typeof jobsApi.reopenJob>[1]) => jobsApi.reopenJob(id, input)); }
