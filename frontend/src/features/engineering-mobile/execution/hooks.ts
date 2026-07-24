import { useQuery } from "@tanstack/react-query";

import { shouldRetryApiQuery } from "../../../api/errors";
import { getExecutionStatus } from "./api";
import type { MobileExecutionStatus } from "./types";

export const DEFAULT_EXECUTION_POLLING_MS = 30_000;
export const MIN_EXECUTION_POLLING_MS = 10_000;
export const MAX_EXECUTION_POLLING_MS = 120_000;

export const executionStatusKey = (commandId: string) =>
  ["engineering-mobile", "execution-status", commandId] as const;

export function executionPollingInterval(
  status: MobileExecutionStatus | undefined,
): number | false {
  if (status?.terminal || status?.polling_after_seconds === null) return false;
  if (status?.polling_after_seconds === undefined) {
    return DEFAULT_EXECUTION_POLLING_MS;
  }
  return Math.min(
    MAX_EXECUTION_POLLING_MS,
    Math.max(MIN_EXECUTION_POLLING_MS, status.polling_after_seconds * 1_000),
  );
}

export function useExecutionStatus(commandId: string | undefined) {
  return useQuery({
    queryKey: executionStatusKey(commandId ?? ""),
    queryFn: () => getExecutionStatus(commandId as string),
    enabled: Boolean(commandId),
    retry: shouldRetryApiQuery,
    refetchInterval: (query) => executionPollingInterval(query.state.data),
    refetchIntervalInBackground: false,
  });
}
