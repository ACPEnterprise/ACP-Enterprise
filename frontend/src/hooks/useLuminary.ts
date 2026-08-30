import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  analyzeLuminary,
  getLuminaryBriefing,
  getLuminarySourceReadiness,
} from "../api/luminary";

export function useLuminaryBriefing(
  start: string,
  end: string,
  enabled = true,
) {
  return useQuery({
    queryKey: ["luminary", "briefing", start, end],
    queryFn: () => getLuminaryBriefing(start, end),
    enabled,
    retry: false,
  });
}

export function useLuminarySourceReadiness(
  start: string,
  end: string,
  enabled = true,
) {
  return useQuery({
    queryKey: ["luminary", "source-readiness", start, end],
    queryFn: () => getLuminarySourceReadiness(start, end),
    enabled,
    retry: false,
  });
}

export function useAnalyzeLuminary(start: string, end: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => analyzeLuminary(start, end),
    onSuccess: (value) =>
      client.setQueryData(["luminary", "briefing", start, end], value),
  });
}
