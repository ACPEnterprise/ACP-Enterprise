import { apiClient } from "./client";
import type {
  EngineeringCommandApproveInput,
  EngineeringCommandCancelInput,
  EngineeringCommandDetail,
  EngineeringCommandListQuery,
  EngineeringCommandPage,
} from "../types/engineeringControl";

const ENGINEERING_COMMANDS_PATH = "/api/v1/engineering-commands";

export async function listEngineeringCommands(
  query: EngineeringCommandListQuery,
): Promise<EngineeringCommandPage> {
  const response = await apiClient.get<EngineeringCommandPage>(
    ENGINEERING_COMMANDS_PATH,
    {
      params: {
        approval_state: query.approvalState,
        page: query.page,
        page_size: query.pageSize,
      },
    },
  );
  return response.data;
}

export async function getEngineeringCommand(
  commandId: string,
): Promise<EngineeringCommandDetail> {
  return (
    await apiClient.get<EngineeringCommandDetail>(
      `${ENGINEERING_COMMANDS_PATH}/${commandId}`,
    )
  ).data;
}

export async function approveEngineeringCommand(
  commandId: string,
  input: EngineeringCommandApproveInput,
): Promise<EngineeringCommandDetail> {
  return (
    await apiClient.post<EngineeringCommandDetail>(
      `${ENGINEERING_COMMANDS_PATH}/${commandId}/approve`,
      input,
    )
  ).data;
}

export async function cancelEngineeringCommand(
  commandId: string,
  input: EngineeringCommandCancelInput,
): Promise<EngineeringCommandDetail> {
  return (
    await apiClient.post<EngineeringCommandDetail>(
      `${ENGINEERING_COMMANDS_PATH}/${commandId}/cancel`,
      input,
    )
  ).data;
}
