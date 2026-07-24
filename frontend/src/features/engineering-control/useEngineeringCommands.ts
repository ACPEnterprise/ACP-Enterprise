import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import * as engineeringApi from "../../api/engineeringControl";
import { shouldRetryApiQuery } from "../../api/errors";
import type {
  EngineeringCommandApproveInput,
  EngineeringCommandCancelInput,
  EngineeringCommandListQuery,
} from "../../types/engineeringControl";

export const engineeringCommandKeys = {
  all: ["engineering-commands"] as const,
  lists: () => ["engineering-commands", "list"] as const,
  list: (query: EngineeringCommandListQuery) =>
    ["engineering-commands", "list", query] as const,
  detail: (id: string) => ["engineering-commands", "detail", id] as const,
};

export function useEngineeringCommands(query: EngineeringCommandListQuery) {
  return useQuery({
    queryKey: engineeringCommandKeys.list(query),
    queryFn: () => engineeringApi.listEngineeringCommands(query),
    retry: shouldRetryApiQuery,
  });
}

export function useEngineeringCommand(commandId: string | undefined) {
  return useQuery({
    queryKey: engineeringCommandKeys.detail(commandId ?? ""),
    queryFn: () => engineeringApi.getEngineeringCommand(commandId as string),
    enabled: Boolean(commandId),
    retry: shouldRetryApiQuery,
  });
}

function useEngineeringMutation<T>(
  commandId: string,
  mutationFn: (input: T) => Promise<{ id: string }>,
) {
  const client = useQueryClient();
  const refresh = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: engineeringCommandKeys.lists() }),
      client.invalidateQueries({
        queryKey: engineeringCommandKeys.detail(commandId),
      }),
    ]);
  };
  return useMutation({
    mutationFn,
    retry: false,
    onSuccess: refresh,
    onError: refresh,
  });
}

export function useApproveEngineeringCommand(commandId: string) {
  return useEngineeringMutation<EngineeringCommandApproveInput>(
    commandId,
    (input) => engineeringApi.approveEngineeringCommand(commandId, input),
  );
}

export function useCancelEngineeringCommand(commandId: string) {
  return useEngineeringMutation<EngineeringCommandCancelInput>(
    commandId,
    (input) => engineeringApi.cancelEngineeringCommand(commandId, input),
  );
}
