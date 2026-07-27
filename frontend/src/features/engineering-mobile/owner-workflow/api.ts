import { apiClient } from "../../../api/client";
import type {
  EngineeringReviewDecisionInput,
  EngineeringReviewPackage,
  ExecuteRepositoryCommitInput,
  RepositoryAuthorizationDetail,
  RepositoryAuthorizationInput,
  RepositoryOperationDetail,
} from "./types";

export const engineeringReviewPath = "/api/v1/engineering/reviews";
export const repositoryAuthorizationPath =
  "/api/v1/engineering/repository-authorizations";
export const repositoryOperationPath =
  "/api/v1/engineering/repository-operations";

export async function prepareEngineeringReview(
  commandId: string,
): Promise<EngineeringReviewPackage> {
  return (
    await apiClient.post<EngineeringReviewPackage>(
      `${engineeringReviewPath}/commands/${commandId}`,
    )
  ).data;
}

export async function getEngineeringReview(
  reviewId: string,
): Promise<EngineeringReviewPackage> {
  return (
    await apiClient.get<EngineeringReviewPackage>(
      `${engineeringReviewPath}/${reviewId}`,
    )
  ).data;
}

export async function decideEngineeringReview(
  reviewId: string,
  input: EngineeringReviewDecisionInput,
): Promise<EngineeringReviewPackage> {
  return (
    await apiClient.post<EngineeringReviewPackage>(
      `${engineeringReviewPath}/${reviewId}/decision`,
      input,
    )
  ).data;
}

export async function requestRepositoryAuthorization(
  input: RepositoryAuthorizationInput,
): Promise<RepositoryAuthorizationDetail> {
  return (
    await apiClient.post<RepositoryAuthorizationDetail>(
      repositoryAuthorizationPath,
      input,
    )
  ).data;
}

export async function getRepositoryAuthorization(
  authorizationId: string,
): Promise<RepositoryAuthorizationDetail> {
  return (
    await apiClient.get<RepositoryAuthorizationDetail>(
      `${repositoryAuthorizationPath}/${authorizationId}`,
    )
  ).data;
}

export async function executeRepositoryCommit(
  input: ExecuteRepositoryCommitInput,
): Promise<RepositoryOperationDetail> {
  return (
    await apiClient.post<RepositoryOperationDetail>(
      `${repositoryOperationPath}/execute`,
      input,
    )
  ).data;
}

export async function getRepositoryOperation(
  operationId: string,
): Promise<RepositoryOperationDetail> {
  return (
    await apiClient.get<RepositoryOperationDetail>(
      `${repositoryOperationPath}/${operationId}`,
    )
  ).data;
}
