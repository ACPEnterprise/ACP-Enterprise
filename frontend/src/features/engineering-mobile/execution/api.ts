import { apiClient } from "../../../api/client";
import type { MobileExecutionStatus } from "./types";

export const executionStatusPath = (commandId: string) =>
  `/api/v1/engineering/mobile/commands/${commandId}/execution-status`;

export async function getExecutionStatus(
  commandId: string,
): Promise<MobileExecutionStatus> {
  return (
    await apiClient.get<MobileExecutionStatus>(executionStatusPath(commandId))
  ).data;
}
