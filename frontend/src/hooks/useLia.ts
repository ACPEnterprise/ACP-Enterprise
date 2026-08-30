import { useMutation, useQuery } from "@tanstack/react-query";
import * as liaApi from "../api/lia";
import { shouldRetryApiQuery } from "../api/errors";

export function useLiaReadiness() {
  return useQuery({ queryKey: ["lia", "readiness"], queryFn: liaApi.getLiaReadiness, retry: shouldRetryApiQuery });
}

export function useOwnerBriefing(enabled = true) {
  return useQuery({ queryKey: ["lia", "briefing"], queryFn: liaApi.getOwnerBriefing, retry: shouldRetryApiQuery, enabled });
}

export function useAskLia() {
  return useMutation({ mutationFn: liaApi.askLia });
}
