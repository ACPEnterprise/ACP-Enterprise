import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  assignPrimary,
  changeCrew,
  getDispatchBoard,
  getEligibleTechnicians,
  markReconciliation,
  releasePrimary,
  reportDispatchException,
  resolveReconciliation,
} from "../api/dispatch";
import type { DispatchExceptionCode } from "../types/dispatch";

export const dispatchKeys = {
  all: ["dispatch"] as const,
  board: (start: string, end: string, branch?: string) =>
    ["dispatch", "board", start, end, branch] as const,
  eligible: (id: string) => ["dispatch", "eligible", id] as const,
};
export function useDispatchBoard(start: string, end: string, branch?: string) {
  return useQuery({
    queryKey: dispatchKeys.board(start, end, branch),
    queryFn: () => getDispatchBoard(start, end, branch),
  });
}
export function useEligibleTechnicians(id?: string) {
  return useQuery({
    queryKey: dispatchKeys.eligible(id ?? ""),
    queryFn: () => getEligibleTechnicians(id as string),
    enabled: Boolean(id),
  });
}
export function useDispatchMutations() {
  const client = useQueryClient();
  const refresh = () =>
    client.invalidateQueries({ queryKey: dispatchKeys.all });
  return {
    assign: useMutation({
      mutationFn: (x: {
        appointmentId: string;
        employeeId: string;
        reason: string;
        version?: number;
      }) => assignPrimary(x.appointmentId, x.employeeId, x.reason, x.version),
      onSuccess: refresh,
    }),
    release: useMutation({
      mutationFn: (x: {
        appointmentId: string;
        version: number;
        reason: string;
      }) => releasePrimary(x.appointmentId, x.version, x.reason),
      onSuccess: refresh,
    }),
    crew: useMutation({
      mutationFn: (x: {
        appointmentId: string;
        employeeId: string;
        version: number;
        reason: string;
        remove?: boolean;
      }) =>
        changeCrew(
          x.appointmentId,
          x.employeeId,
          x.version,
          x.reason,
          x.remove,
        ),
      onSuccess: refresh,
    }),
    reconcile: useMutation({
      mutationFn: (x: {
        appointmentId: string;
        version: number;
        reason: string;
        resolution?: "restore_assigned" | "release";
      }) =>
        x.resolution
          ? resolveReconciliation(
              x.appointmentId,
              x.version,
              x.reason,
              x.resolution,
            )
          : markReconciliation(x.appointmentId, x.version, x.reason),
      onSuccess: refresh,
    }),
    exception: useMutation({
      mutationFn: (x: {
        appointmentId: string;
        version: number;
        reason: string;
        exceptionCode: DispatchExceptionCode;
      }) =>
        reportDispatchException(
          x.appointmentId,
          x.version,
          x.reason,
          x.exceptionCode,
        ),
      onSuccess: refresh,
    }),
  };
}
