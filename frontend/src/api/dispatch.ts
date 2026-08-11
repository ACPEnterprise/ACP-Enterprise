import { apiClient } from "./client";
import type {
  DispatchAssignment,
  DispatchBoardPage,
  TechnicianEligibility,
  DispatchExceptionCode,
} from "../types/dispatch";

const ROOT = "/api/v1/dispatch";
export async function getDispatchBoard(
  startAt: string,
  endAt: string,
  branchId?: string,
): Promise<DispatchBoardPage> {
  return (
    await apiClient.get<DispatchBoardPage>(`${ROOT}/board`, {
      params: { start_at: startAt, end_at: endAt, branch_id: branchId },
    })
  ).data;
}
export async function getEligibleTechnicians(
  appointmentId: string,
): Promise<readonly TechnicianEligibility[]> {
  return (
    await apiClient.get<readonly TechnicianEligibility[]>(
      `${ROOT}/appointments/${appointmentId}/eligible-technicians`,
    )
  ).data;
}
export async function assignPrimary(
  appointmentId: string,
  employeeId: string,
  reason: string,
  expectedVersion?: number,
): Promise<DispatchAssignment> {
  const path = `${ROOT}/appointments/${appointmentId}/assignment${expectedVersion ? "/primary" : ""}`;
  const method = expectedVersion ? apiClient.put : apiClient.post;
  return (
    await method<DispatchAssignment>(path, {
      employee_id: employeeId,
      reason,
      idempotency_key: crypto.randomUUID(),
      expected_version: expectedVersion,
    })
  ).data;
}
export async function releasePrimary(
  appointmentId: string,
  version: number,
  reason: string,
): Promise<DispatchAssignment> {
  return (
    await apiClient.delete<DispatchAssignment>(
      `${ROOT}/appointments/${appointmentId}/assignment/primary`,
      {
        data: {
          reason,
          idempotency_key: crypto.randomUUID(),
          expected_version: version,
        },
      },
    )
  ).data;
}
export async function changeCrew(
  appointmentId: string,
  employeeId: string,
  version: number,
  reason: string,
  remove = false,
): Promise<DispatchAssignment> {
  const config = {
    data: {
      employee_id: employeeId,
      reason,
      idempotency_key: crypto.randomUUID(),
      expected_version: version,
    },
  };
  return remove
    ? (
        await apiClient.delete<DispatchAssignment>(
          `${ROOT}/appointments/${appointmentId}/assignment/crew`,
          config,
        )
      ).data
    : (
        await apiClient.post<DispatchAssignment>(
          `${ROOT}/appointments/${appointmentId}/assignment/crew`,
          config.data,
        )
      ).data;
}
export async function markReconciliation(
  appointmentId: string,
  version: number,
  reason: string,
): Promise<DispatchAssignment> {
  return (
    await apiClient.post<DispatchAssignment>(
      `${ROOT}/appointments/${appointmentId}/assignment/reconciliation-required`,
      {
        reason,
        idempotency_key: crypto.randomUUID(),
        expected_version: version,
      },
    )
  ).data;
}
export async function reportDispatchException(
  appointmentId: string,
  version: number,
  reason: string,
  exceptionCode: DispatchExceptionCode,
): Promise<DispatchAssignment> {
  return (
    await apiClient.post<DispatchAssignment>(
      `${ROOT}/appointments/${appointmentId}/assignment/exceptions`,
      {
        reason,
        exception_code: exceptionCode,
        idempotency_key: crypto.randomUUID(),
        expected_version: version,
      },
    )
  ).data;
}
export async function resolveReconciliation(
  appointmentId: string,
  version: number,
  reason: string,
  resolution: "restore_assigned" | "release",
): Promise<DispatchAssignment> {
  return (
    await apiClient.post<DispatchAssignment>(
      `${ROOT}/appointments/${appointmentId}/assignment/reconcile`,
      {
        reason,
        idempotency_key: crypto.randomUUID(),
        expected_version: version,
        resolution,
      },
    )
  ).data;
}
