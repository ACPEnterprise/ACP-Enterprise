import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { shouldRetryApiQuery } from "../../../api/errors";
import { executionStatusKey } from "../execution/hooks";
import * as ownerApi from "./api";
import type {
  EngineeringReviewDecisionInput,
  ExecuteRepositoryCommitInput,
  RepositoryAuthorizationInput,
} from "./types";

export const ownerWorkflowKeys = {
  review: (reviewId: string) =>
    ["engineering-mobile", "owner-review", reviewId] as const,
  authorization: (authorizationId: string) =>
    ["engineering-mobile", "repository-authorization", authorizationId] as const,
  operation: (operationId: string) =>
    ["engineering-mobile", "repository-operation", operationId] as const,
};

function useStatusInvalidation(commandId: string) {
  const queryClient = useQueryClient();
  return async () => {
    await queryClient.invalidateQueries({
      queryKey: executionStatusKey(commandId),
    });
  };
}

export function useEngineeringOwnerReview(reviewId: string | undefined) {
  return useQuery({
    queryKey: ownerWorkflowKeys.review(reviewId ?? ""),
    queryFn: () => ownerApi.getEngineeringReview(reviewId as string),
    enabled: Boolean(reviewId),
    retry: shouldRetryApiQuery,
  });
}

export function usePrepareEngineeringReview(commandId: string) {
  const invalidateStatus = useStatusInvalidation(commandId);
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => ownerApi.prepareEngineeringReview(commandId),
    retry: false,
    onSuccess: async (review) => {
      queryClient.setQueryData(ownerWorkflowKeys.review(review.review.id), review);
      await invalidateStatus();
    },
  });
}

export function useDecideEngineeringReview(
  commandId: string,
  reviewId: string,
) {
  const invalidateStatus = useStatusInvalidation(commandId);
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: EngineeringReviewDecisionInput) =>
      ownerApi.decideEngineeringReview(reviewId, input),
    retry: false,
    onSuccess: async (review) => {
      queryClient.setQueryData(ownerWorkflowKeys.review(reviewId), review);
      await invalidateStatus();
    },
  });
}

export function useRepositoryAuthorization(
  authorizationId: string | undefined,
) {
  return useQuery({
    queryKey: ownerWorkflowKeys.authorization(authorizationId ?? ""),
    queryFn: () =>
      ownerApi.getRepositoryAuthorization(authorizationId as string),
    enabled: Boolean(authorizationId),
    retry: shouldRetryApiQuery,
  });
}

export function useRequestRepositoryAuthorization(commandId: string) {
  const invalidateStatus = useStatusInvalidation(commandId);
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: RepositoryAuthorizationInput) =>
      ownerApi.requestRepositoryAuthorization(input),
    retry: false,
    onSuccess: async (authorization) => {
      queryClient.setQueryData(
        ownerWorkflowKeys.authorization(authorization.id),
        authorization,
      );
      await invalidateStatus();
    },
  });
}

export function useRepositoryOperation(operationId: string | undefined) {
  return useQuery({
    queryKey: ownerWorkflowKeys.operation(operationId ?? ""),
    queryFn: () => ownerApi.getRepositoryOperation(operationId as string),
    enabled: Boolean(operationId),
    retry: shouldRetryApiQuery,
  });
}

export function useExecuteRepositoryCommit(commandId: string) {
  const invalidateStatus = useStatusInvalidation(commandId);
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ExecuteRepositoryCommitInput) =>
      ownerApi.executeRepositoryCommit(input),
    retry: false,
    onSuccess: (operation) => {
      queryClient.setQueryData(
        ownerWorkflowKeys.operation(operation.id),
        operation,
      );
    },
    onSettled: invalidateStatus,
  });
}
